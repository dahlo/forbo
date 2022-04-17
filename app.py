import tornado.ioloop
import tornado.web
import os
import yaml
import re
import logging
from datetime import date
import base64
#import zlib




logging.basicConfig(format="{asctime} {threadName:>11} {levelname} {message}", 
                    style='{',
                    level=logging.DEBUG,
                    )




def get_periods():
    # list directories
    periods = [d.name for d in os.scandir('invoices') if d.is_dir()]

    # if there are no periods, create one for the current year
    if len(periods) == 0:
            current_year = str(date.today().year)
            logging.debug(f'No periods found, creating one for {current_year}')
            os.mkdir(os.path.join('invoices', current_year))
            return [current_year]

    return periods



def get_invoices(current_period):
    
    # list invoices from period
    try:
        invoices = sorted(os.listdir(os.path.join('invoices', current_period)))
    except FileNotFoundError:
        logging.debug(f'Period dir not listable ({os.path.join("invoices", current_period)}).')
        return {'in':[],'out':[]}

    # split invoices into deposits and withdrawals
    invoice_lists = {'in':[], 'out':[]}
    for invoice in invoices:

        invoice_split = invoice.split('_-_')
        
        # get invoice info
        invoice_element = {}
        invoice_element['id'] = invoice_split[0]
        invoice_element['date'] = invoice_split[1]
        invoice_element['amount'] = float(invoice_split[2].replace(',','.'))
        invoice_element['name'] = invoice_split[3]
        invoice_element['tags'] = invoice_split[4]
        invoice_element['notes'] = base64.b64decode(invoice_split[5].encode()).decode('utf-8')
        invoice_element['filename'] = invoice_split[6]

        # separate deposits from withdrawals
        if invoice_element['amount'] > 0:
            invoice_lists['in'].append(invoice_element)
        else:
            invoice_lists['out'].append(invoice_element)

    return invoice_lists




def get_next_index(period):

    # list files
    try:
        a.encoinvoices = os.listdir(os.path.join('invoices', period))

    # if the period dir does not exist yet
    except FileNotFoundError:
        logging.debug(f'Period not found, creating one for {period}')
        os.mkdir(os.path.join('invoices', period))
        invoices = []

    # if the list is empty
    if len(invoices) == 0:
        return "0".zfill(4)

    # pick out indexes
    indexes = [int(i.split('_-_')[0]) for i in invoices]

    # return the maximum one + 1
    return str(max(indexes)+1).zfill(4)



class MainHandler(tornado.web.RequestHandler):
    def get(self):

        logging.debug('Running main handler.')

        # list invoice folder
        periods = get_periods()

        # set current period
        current_period = periods[-1]

        # get invoices from current period
        invoices = get_invoices(current_period)

        # render page
        self.render("home.html", title=config['site_name'], deposits=invoices['in'], withdrawals=invoices['out'])




class AddHandler(tornado.web.RequestHandler):
    def get(self):
        self.render("add.html", title=config['site_name'], current_period=get_periods()[-1])


    def post(self):

        # get post data
        period = self.get_argument('period')
        invoice_date = self.get_argument('date')
        amount = self.get_argument('amount')
        name = self.get_argument('name')
        tags = self.get_argument('tags')
        notes = self.get_argument('notes')
        invoice_file = self.request.files['invoice_file'][0]

        # base64 encode the notes
        notes_bytes = notes.encode('utf-8')
        notes64_bytes = base64.b64encode(notes_bytes)
        notes64 = notes64_bytes.decode('utf-8')
        
        # get next index to use in the period
        index = get_next_index(period)

        # compress notes string
        #notes64 = base64.b64encode(zlib.compress(notes.encode())).decode('utf-8')

        # construct file name
        file_name = f"{index}_-_{invoice_date}_-_{amount}_-_{name}_-_{tags}_-_{notes64}_-_{invoice_file['filename']}"

        # write file
        with open(os.path.join('invoices', period, file_name), 'wb') as ifh:
            ifh.write(invoice_file['body'])

        self.finish(f'<html>Ny händelse sparad, återgår till startsidan om 3 sekunder.<meta http-equiv="Refresh" content="3; url=\'/\'" /></html>')



def make_app(settings=None):
    return tornado.web.Application([
            (r"/", MainHandler),
            (r"/add", AddHandler),

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



    settings = {"template_path": os.path.join(os.path.dirname(__file__), "forbo", "templates"),
                "static_path": os.path.join(os.path.dirname(__file__), "forbo", "static"),
                
                }
    
    app = make_app(settings = settings)
    logging.info("Starting web server on port 8888.")
    app.listen(8888)
    tornado.ioloop.IOLoop.current().start()

