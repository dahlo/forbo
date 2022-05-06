import tornado.ioloop
import tornado.web
import os
import yaml
import re
import logging
import datetime
import base64
#import zlib
import sqlite3
import shutil

import pdb


logging.basicConfig(format="{asctime} {threadName:>11} {levelname} {message}", 
        style='{',
        level=logging.DEBUG,
        )


def add_period(cur, period, start_balance=None, end_balance=None, notes=None):

    try:
        # create period
        cur.execute("INSERT INTO periods(period, start_balance, end_balance, notes) VALUES(?,?,?,?)", [period, start_balance, end_balance, notes])

    # period name not unique, throw error
    except sqlite3.IntegrityError:
        pass


def get_periods(cur):

    res = cur.execute("SELECT * FROM periods").fetchall()

    periods = {}
    for row in res:
        periods[row['period']] = dict(row)

    # if there are no periods defined yet
    if len(periods) == 0:

        # create a period for the current year
        current_year = datetime.datetime.today().year
        add_period(cur=cur, period=current_year)
        periods = get_periods(cur)

    return periods



def get_invoices(cur, current_period):

    # get invoice list from db
    res = cur.execute("SELECT * FROM invoices WHERE period=?", [current_period]).fetchall()

    invoice_lists = {'in':[], 'out':[]}
    for row in res:

        # get invoice info
        invoice_element = dict(row)
        invoice_element['filename'] = os.path.basename(row['file_path'])

        # separate deposits from withdrawals
        if invoice_element['amount'] > 0:
            invoice_lists['in'].append(invoice_element)
        else:
            invoice_lists['out'].append(invoice_element)

    return invoice_lists





def get_invoice(cur, id):

    # fetch db record
    res = cur.execute("SELECT * FROM invoices WHERE id=?", [id]).fetchone()

    # return as dict
    return dict(row)




def create_db():

    logging.info("Creating new database.")

    # make sure the file doesn't exist yet, and move the old db to a new name before creating a new empty one
    if os.path.exists("forbo/db.sqlite"):
        logging.warning(f"Old database found. Moving to new name to not overwrite it, forbo/db.sqlite.{datetime.datetime.now().strftime('%Y-%M-%d_%H%m%S')}")
        shutil.move("forbo/db.sqlite", f"forbo/db.sqlite.{datetime.datetime.now().strftime('%Y-%M-%d_%H%m%S')}")

    shutil.copy("forbo/db.sqlite.dist", "forbo/db.sqlite")
    logging.debug("New database created.")



def connect_db():

    # create db if it does not exist
    if not os.path.exists('forbo/db.sqlite'):
        create_db()

    # connect to db
    logging.info("Connecting to database.")
    db = sqlite3.connect("forbo/db.sqlite")

    # get dict like results from db
    db.row_factory = sqlite3.Row

    # create cursor
    cur = db.cursor()

    return db, cur




def get_category_tags(cur):

    #pdb.set_trace()
    # select all defined category tags
    categories = cur.execute(f"SELECT DISTINCT category FROM invoices").fetchall()

    # get the predefined categories from config file
    predef_cats = config['categories']

    # merge lists
    cats = set()
    for cat in categories:
        cats.add(cat['category'])
    for cat in predef_cats.split(','):
        cats.add(cat)

    # merge to a quoted list
    cat_list = ""
    for cat in cats:
        cat_list += f"\"{cat}\", "



    return cat_list 





class MainHandler(tornado.web.RequestHandler):

    def initialize(self, cur):
        self.cur = cur

    def get(self):

        logging.debug('Running main handler.')
        
        # list invoice folder
        periods = get_periods(self.cur)

        # set current period
        current_period = self.get_cookie("current_period")
        if not current_period:
            current_period = sorted(periods.keys())[-1]
            self.set_cookie("current_period", current_period)


        # get invoices from current period
        invoices = get_invoices(self.cur, current_period)

        # get all previous categories
        category_tags = get_category_tags(self.cur)
        
        # render page
        self.render("home.html", title=config['site_name'], periods=periods, deposits=invoices['in'], withdrawals=invoices['out'], current_period=current_period, category_tags=category_tags)




class AddHandler(tornado.web.RequestHandler):
    
    def initialize(self, db, cur):
        self.db = db
        self.cur = cur
    
    def get(self, direction="out"):
        if not direction:
            direction = "out"

        # get current period
        current_period = self.get_cookie("current_period")
        if not current_period:
            current_period = get_periods()[-1]
            self.set_cookie("current_period", current_period)

        self.render("add.html", title=config['site_name'], current_period=current_period, direction=direction)



class NotFoundHandler(tornado.web.RequestHandler):
    def get(self):
        self.render("404.html", title=config['site_name'])



class ApiAddInvoiceHandler(tornado.web.RequestHandler):
    
    def initialize(self, db, cur):
        self.db = db
        self.cur = cur

    def post(self, direction=None):

        # get post data
        period = self.get_argument('period')
        date = self.get_argument('date')
        amount = float(self.get_argument('amount'))
        description = self.get_argument('description')
        category = self.get_argument('category')
        notes = self.get_argument('notes')
        direction = self.get_argument('direction') # get no more than 3 characters
        invoice_file = self.request.files['invoice_file'][0]

        # compress notes string
        #notes64 = base64.b64encode(zlib.compress(notes.encode())).decode('utf-8')

        # set transaction direction
        if direction == "out":
            amount *= -1

        # insert info
        self.cur.execute("INSERT INTO invoices(period, date, amount, description, category, notes) VALUES(?,?,?,?,?,?)", [period, date, amount, description, category, notes])

        # get id of insert
        last_id = self.cur.lastrowid

        # construct file name
        file_name = f"{last_id}_{invoice_file['filename']}"

        # write file
        with open(os.path.join('invoices', period, file_name), 'wb') as ifh:
            ifh.write(invoice_file['body'])

        self.cur.execute("UPDATE invoices SET file_path=? WHERE id=?", [os.path.join('invoices', period, file_name), last_id])
        self.db.commit()

        self.finish(f'<html>Ny händelse sparad, återgår till startsidan om 3 sekunder.<meta http-equiv="Refresh" content="3; url=\'/\'" /></html>')







class ApiRemoveInvoiceHandler(tornado.web.RequestHandler):
    
    def initialize(self, db, cur):
        self.db = db
        self.cur = cur

    def post(self, direction=None):

        # get post data
        id = self.get_argument('id')

        logging.info(f"Deleting invoice {id}")

        # fetch db entry
        logging.debug(f"Fetching db record {id}")
        row = self.cur.execute("SELECT * FROM invoices WHERE id=?", [id]).fetchone()

        # delete file if any
        if row['file_path']:
            logging.debug(f"Removing file {row['file_path']}")
            try:
                os.remove(row['file_path'])
            except FileNotFoundError:
                logging.debug(f"File not found, continuing.")

        # delete db entry
        logging.debug(f"Removing db record {id}")
        self.cur.execute("DELETE FROM invoices WHERE id=?", [id])
        self.db.commit()


        self.finish(f'<html>Händelse borttagen, återgår till startsidan om 3 sekunder.<meta http-equiv="Refresh" content="3; url=\'/\'" /></html>')





class EditInvoiceHandler(tornado.web.RequestHandler):
    
    def initialize(self, db, cur):
        self.db = db
        self.cur = cur
    
    def get(self, id):

        # fetch invoice info from db
        invoice = get_invoice(self.cur, id)




def make_app(settings=None):
    
    # connect to db
    db, cur = connect_db()

    return tornado.web.Application([
        (r"/", MainHandler, dict(cur=cur)),
        (r"/add/*(\bin\b|\bout\b)*", AddHandler, dict(db=db, cur=cur)),
        (r"/edit/invoice/?id=(\d+)", EditInvoiceHandler, dict(db=db, cur=cur)),
        (r"/api/add/invoice", ApiAddInvoiceHandler, dict(db=db, cur=cur)),
        (r"/api/remove/invoice", ApiRemoveInvoiceHandler, dict(db=db, cur=cur)),
        (r".*", NotFoundHandler),
        ],
        ** settings,
        )




if __name__ == "__main__":

        # change workdir to scripts dir
    os.chdir(os.path.abspath(os.path.dirname(__file__)))

    # load config file if exists
    try:
        with open(r'config.yaml') as config_file:
            config = yaml.load(config_file, Loader=yaml.FullLoader)
    except FileNotFoundError:
        logging.warning("Config file not found, creating default config.")

        # create a default config file
        config = {  'site_name':'Förenklat bokslut',
                }

        with open(r'config.yaml', 'w') as config_file:
            yaml.dump(config, config_file)
            logging.debug('Writing default config file.')


    # tornado settings
    settings = {"template_path": os.path.join(os.path.dirname(__file__), "forbo", "templates"),
            "static_path": os.path.join(os.path.dirname(__file__), "forbo", "static"),

            }



    # start the server
    app = make_app(settings = settings)
    logging.info("Starting web server on port 8888.")
    app.listen(8888)
    tornado.ioloop.IOLoop.current().start()

