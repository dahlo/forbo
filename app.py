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
from pathlib import Path

import pdb


logging.basicConfig(format="{asctime} {threadName:>11} {levelname} {message}", 
        style='{',
        level=logging.DEBUG,
        )



def sanitize_input(text):

    # skip None type objects
    if text==None:
        return None

    # remove anything weird
    text = re.sub(r'[^\wåäö\-\.,\s\?\!]', '', text)

    return text



def error_message(self, msg):
    self.finish(f'<html>{msg}, återgår till startsidan om 3 sekunder.<meta http-equiv="Refresh" content="3; url=\'/\'" /></html>')



def add_period(cur, db, period, start_balance=None, end_balance=None, notes=None):

    try:
        # create period
        cur.execute("INSERT INTO periods(period, start_balance, end_balance, notes) VALUES(?,?,?,?)", [period, start_balance, end_balance, notes])
        db.commit()

    # period name not unique, throw error
    except sqlite3.IntegrityError:
        pass


def get_periods(cur, db):

    res = cur.execute("SELECT * FROM periods").fetchall()

    periods = {}
    for row in res:
        periods[row['period']] = dict(row)

    # if there are no periods defined yet
    if len(periods) == 0:

        # create a period for the current year
        current_year = datetime.datetime.today().year
        add_period(cur=cur, db=db, period=current_year)
        periods = get_periods(cur, db)

    return periods



def get_invoices(cur, current_period):

    # get invoice list from db
    res = cur.execute("SELECT * FROM invoices WHERE period=?", [current_period]).fetchall()

    invoice_lists = {'in':[], 'out':[]}
    for row in res:

        # get invoice info
        invoice_element = dict(row)

        if row['file_path']:
            # remove the invoice id from the file name when displaying it on the site
            invoice_element['filename'] = "_".join(os.path.basename(row['file_path']).split("_")[1:])
        else:
            invoice_element['filename'] = None

	# set all empty values to dash
        for key,val in invoice_element.items():
            if not val:
                invoice_element[key] = "-"

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
    return dict(res)




def create_db():

    logging.info("Creating new database.")

    # make sure the file doesn't exist yet, and move the old db to a new name before creating a new empty one
    if os.path.exists("fobos/db.sqlite"):
        logging.warning(f"Old database found. Moving to new name to not overwrite it, fobos/db.sqlite.{datetime.datetime.now().strftime('%Y-%M-%d_%H%m%S')}")
        shutil.move("fobos/db.sqlite", f"fobos/db.sqlite.{datetime.datetime.now().strftime('%Y-%M-%d_%H%m%S')}")

    shutil.copy("fobos/db.sqlite.dist", "fobos/db.sqlite")
    logging.debug("New database created.")



def connect_db():

    # create db if it does not exist
    if not os.path.exists('fobos/db.sqlite'):
        create_db()

    # connect to db
    logging.info("Connecting to database.")
    db = sqlite3.connect("fobos/db.sqlite")

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



# serve a general file
def serve_file(path, filename=None):
        if not os.path.isfile(path):
            raise tornado.web.HTTPError(status_code=404)
        self.set_header('Content-Type', 'application/octet-stream')

        # set file name if specified
        if filename:
            self.set_header('Content-Disposition', 'attachment; filename=' + filename)

        # set bufer size
        buf_size = 4096
        with open(path) as source_file:
            while True:
                date = source_file.read(buf_size)
                if not data:
                    break
                self.write(source_file.read())
        self.finish()



class MainHandler(tornado.web.RequestHandler):

    def initialize(self, cur, db):
        self.cur = cur
        self.db = db

    def get(self):

        logging.debug('Running main handler.')
        
        # list invoice folder
        periods = get_periods(self.cur, self.db)

        # set current period
        current_period = self.get_cookie("current_period")

        # see if there is a matching period
        if current_period not in periods.keys():
            logging.debug(f"Current period not a valid period, {current_period}, setting default period.")
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
            current_period = get_periods(self.cur, self.db)[-1]
            self.set_cookie("current_period", current_period)

        self.render("add.html", title=config['site_name'], current_period=current_period, direction=direction)



class NotFoundHandler(tornado.web.RequestHandler):
    def get(self):
        self.render("404.html", title=config['site_name'])



class ApiHandler(tornado.web.RequestHandler):

    def initialize(self, db, cur):
        self.db = db
        self.cur = cur


    # post router
    def post(self, api_route=None):

        # if the add invoice button was pressed
        if self.get_argument('add-button-in', None):
            self.invoice_add("in")
        elif self.get_argument('add-button-out', None):
            self.invoice_add("out")

        # anything not matching defined routes
        else:
            return NotFoundHandler()



    # get router
    def get(self, api_route=None):

        # split route
        route = api_route.split('/')
        pdb.set_trace()
        #pdb.set_trace()
        # send invoice requests to the invoice function
        if route[0] == 'invoice':
            return self.invoice(route[1:])

        # send period requests to the period function
        elif route[0] == 'period':
            return self.period(route[1:])

        # anything not matching defined routes
        else:
            return 




    def invoice(self, route):

        if route[0].startswith('download'):
            
            # get the requestid invoice id
            id = self.get_argument('id')

            invoice = get_invoice(self.cur, id)
            self.invoice_download(invoice)
            pass

        else:
            return



    def invoice_download(self, invoice):

        pdb.set_trace()
        # get the original file name

        org_filename = "_".join(os.path.basename(invoice['file_path']).split('_')[1:])

        path = invoice['file_path']

        if not os.path.isfile(path):
            raise tornado.web.HTTPError(status_code=404)
        self.set_header('Content-Type', 'application/octet-stream')

        # set file name
        self.set_header('Content-Disposition', 'attachment; filename=' + org_filename)

        # set bufer size
        buf_size = 4096
        with open(path) as source_file:
            while True:
                date = source_file.read(buf_size)
                if not data:
                    break
                self.write(source_file.read())
        self.finish()







def invoice_add(self, direction=None):

        # get post data
        period = sanitize_input(self.get_cookie('current_period'))
        date = sanitize_input(self.get_argument('date', None))
        amount = self.get_argument('amount', None)
        description = sanitize_input(self.get_argument('description', None))
        category = sanitize_input(self.get_argument('category', None))
        notes = sanitize_input(self.get_argument('notes', None))

        # convert to number
        try:
            amount = float(amount)

            # change sign depending on direction
            if direction == "in":
                amount = abs(amount)
            elif direction == "out":
                amount = -abs(amount)
            
        except ValueError:
            amount = None

        # get invoice file
        try:
            invoice_file = self.request.files['invoice_file'][0]
        except KeyError:
            invoice_file = None

        # compress notes string
        #notes64 = base64.b64encode(zlib.compress(notes.encode())).decode('utf-8')

        # check if period exists
        periods = get_periods(self.cur, self.db)
        if period not in periods.keys():
            error_message(self, "Perioden finns inte")
            return


        # check for missing values
        if not amount:
            error_message(self, "Inget belopp angivet")
            return

        # insert info
        self.cur.execute("INSERT INTO invoices(period, date, amount, description, category, notes) VALUES(?,?,?,?,?,?)", [period, date, amount, description, category, notes])

        # get id of insert
        last_id = self.cur.lastrowid

        if invoice_file:
            # construct file name
            file_name = f"{last_id}_{invoice_file['filename']}"

            # create invoice folder if needed
            Path(os.path.join('invoices', period)).mkdir(parents=True, exist_ok=True)
        
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
        id = santitize_input(self.get_argument('id'))

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







class ApiPeriodModifyHandler(tornado.web.RequestHandler):

    def initialize(self, db, cur):
        self.db = db
        self.cur = cur

    def post(self):

        # get post data
        period_selected         = sanitize_input(self.get_argument('period_select', None))
        rem_period              = sanitize_input(self.get_argument('period-remove', None))
        add_period              = sanitize_input(self.get_argument('period-add', None))
        new_period_name         = sanitize_input(self.get_argument('period-add-name', None))
        new_period_start_balance= sanitize_input(self.get_argument('period-add-start-balance', None))
        new_period_end_balance  = sanitize_input(self.get_argument('period-add-end-balance', None))
        new_period_notes        = sanitize_input(self.get_argument('period-add-notes', None))


        # if a new period is to be added
        if add_period:

            # check if a new name is given
            if not new_period_name:
                logging.warning(f"New period name not defined, unable to add new period.")
                self.finish(f'<html>Inget periodnamn givet, återgår till startsidan om 3 sekunder.<meta http-equiv="Refresh" content="3; url=\'/\'" /></html>')
                return

            logging.debug(f"Adding new period {new_period_name}")

            try:
                self.cur.execute("INSERT INTO periods(period, start_balance, end_balance, notes) VALUES(?,?,?,?)", [new_period_name, new_period_start_balance, new_period_end_balance, new_period_notes])
                self.db.commit()
            except sqlite3.IntegrityError:
                logging.error(f"Period already exists: {new_period_name}")
                self.finish(f'<html>Period med samma namn finns redan, återgår till startsidan om 3 sekunder.<meta http-equiv="Refresh" content="3; url=\'/\'" /></html>')
           
            # set new period as active
            self.set_cookie("current_period", new_period_name)

            # create period folder
            logging.debug(f"Creating new folder for period {new_period_name}")
            os.mkdir(f"invoices/{new_period_name}")

            self.finish(f'<html>Ny period sparad, återgår till startsidan om 3 sekunder.<meta http-equiv="Refresh" content="3; url=\'/\'" /></html>')

        elif rem_period:

            # fetch all invoices from the selected period
            for invoice in self.cur.execute("SELECT * FROM invoices WHERE period=?", [period_selected]).fetchall():

                # remove any attachments
                if invoice['file_path']:
                    logging.debug(f"Removing invoice attachment {invoice['file_path']}")
                    os.remove(invoice['file_path'])

                # remove db entry
                logging.debug(f"Removing invoice db entry {invoice['id']}")
                self.cur.execute("DELETE FROM invoices WHERE id=?", [invoice['id']])
            
            logging.debug(f"Removing period {period_selected}")
            self.cur.execute("DELETE FROM periods WHERE period=?", [period_selected])
            self.db.commit()

            # remove period folder
            os.rmdir(f"invoices/{period_selected}")

            # reset cookie period
            self.clear_cookie("current_period")

            self.finish(f'<html>Period borttagen, återgår till startsidan om 3 sekunder.<meta http-equiv="Refresh" content="3; url=\'/\'" /></html>')






def make_app(settings=None):
    
    # connect to db
    db, cur = connect_db()

    return tornado.web.Application([
        (r"/", MainHandler, dict(cur=cur, db=db)),
        (r"/api/(.+)", ApiHandler, dict(db=db, cur=cur)),
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
    settings = {"template_path": os.path.join(os.path.dirname(__file__), "fobos", "templates"),
            "static_path": os.path.join(os.path.dirname(__file__), "fobos", "static"),

            }



    # start the server
    app = make_app(settings = settings)
    logging.info("Starting web server on port 8888.")
    app.listen(8888)
    tornado.ioloop.IOLoop.current().start()

