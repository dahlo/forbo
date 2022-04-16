import tornado.ioloop
import tornado.web
import os
import yaml
import re
import logging

# set up logging
log = logging.getLogger("mylog")
log.setLevel(logging.DEBUG)

formatter = logging.Formatter(
#    "%(asctime)s %(threadName)-11s %(levelname)-10s %(message)s")
# Alternative formatting available on python 3.2+:
# formatter = logging.Formatter(
     "{asctime} {threadName:>11} {levelname} {message}", style='{')

# Log to stdout too
streamhandler = logging.StreamHandler()
streamhandler.setFormatter(formatter)
log.addHandler(streamhandler)


def get_periods():
    return os.listdir('invoices')

def get_invoices(current_period):
    
    # list invoices from period
    try:
        invoices = os.listdir(os.path.join('invoices', current_period))
    except FileNotFoundError:
        log.debug('Period dir not listable.')
        return {'in':[],'out':[]}

    return {'in':['in1', 'in2'], 'out':['out1', 'out2']}

    # split invoices into deposits and withdrawals
    for invoice in invoices:

        # split file name and pick out elements
        pass


    return invoices

class MainHandler(tornado.web.RequestHandler):
    def get(self):

        # list invoice folder
        periods = get_periods()

        # set current period, if there is one
        try:
            current_period = periods[-1]
        except IndexError:
            log.debug('No periods found.')
            current_period = "-"

        invoices = get_invoices(current_period)



        self.render("index.html", title=config['site_name'], deposits=invoices['in'], withdrawals=invoices['out'])






def make_app(settings=None):
    return tornado.web.Application([
            (r"/", MainHandler),

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
        log.warning("Config file not found, creating default config.")

        # create a default config file
        config = {  'site_name':'Förenklat bokslut',
                 }

        with open(r'config.yaml', 'w') as config_file:
            yaml.dump(config, config_file)
            log.debug('Writing default config file.')



    settings = {"template_path": os.path.join(os.path.dirname(__file__), "forbo", "templates"),
                "static_path": os.path.join(os.path.dirname(__file__), "forbo", "static"),
                
                }
    
    app = make_app(settings = settings)
    app.listen(8888)
    tornado.ioloop.IOLoop.current().start()

