#!/usr/env/bin python
import json
import requests
import threading
import time
from datetime import datetime
import serial
import sys, os
import random
import Tkinter as tk

"""
Controller Class

SUPPORT:
JSON-only communication messages.

FUNCTIONS:
checksum()
parse()
reset()
"""
class Controller:
    def __init__(self, device="/dev/ttyACM0", baud=9600, config='v1', dummy=False):
        if type(config) == dict:
            self.conf = config
        else:
            cd = os.getcwd()
            configpath = os.path.join(cd, 'sketches', config, config + '.ctrl')
            with open(configpath) as jsonfile:
                self.conf = self.byteify(json.loads(jsonfile.read()))
        # .ctrl config needs these
        self.check = self.conf['checksum']
        self.data = self.conf['data']
        self.dummy = dummy
        if self.dummy:
            self.port = None
        else:
            self.port = serial.Serial(device, baud)
    def byteify(self, input):
        if isinstance(input, dict):
            return {self.byteify(key) : self.byteify(value) for key,value in input.iteritems()}
        elif isinstance(input, list):
            return [self.byteify(element) for element in input]
        elif isinstance(input, unicode):
            return input.encode('utf-8')
        else:
            return input
    def parse(self, interval=1.0, chars=256):
        if self.dummy:
            v = str(self.data).replace('\'', '\"')
            s = "{\"chksum\":%d,\"data\":%s}" % (self.check, v)
        else:
            s = self.port.readline() #!TODO Need to handle very highspeed controllers, i.e. backlog
        try:
            d = json.loads(s) # parse as JSON
            if self.checksum(d): # Checksum of parsed dictionary
                return d
            else:
                return None
        except Exception as e:
            print str(e)
            return None
    def random(self, n):
        r = [random.randint(0,i) for i in range(n)]
        return r
    def checksum(self, d, mod=256):
        b = d['chksum']
        chksum = 0
        s = str(d)
        s_clean = s.replace(' ', '')
        for i in s_clean:
            chksum += ord(i)
        return chksum % mod
    def reset(self):
        pass

class GUI(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
    def run(self):
        self.root = tk.Tk()
        self.root.title("Hydroponics Controller")
        self.root.geometry("1200x600")
        [self.root.rowconfigure(i,weight=1) for i in range(12)]
        [self.root.columnconfigure(i,weight=1) for i in range(3)]
        
        # Lights
        self.lights_on = tk.DoubleVar()
        self.lights_off = tk.DoubleVar()
        scale_lights_on = tk.Scale(self.root, from_=0.0, to=24.0, length=200, orient=tk.HORIZONTAL, variable = self.lights_on)
        scale_lights_on.grid(column=0, row=2, ipady=20)
        scale_lights_on.set(6)
        scale_lights_off = tk.Scale(self.root, from_=0.0, to=24.0, length=200, orient=tk.HORIZONTAL, variable = self.lights_off)
        scale_lights_off.grid(column=0, row=3, ipady=20)
        scale_lights_off.set(18)
        
        # Watering
        self.watering_time = tk.DoubleVar()
        scale_watering_time = tk.Scale(self.root, from_=0.0, to=60.0, length=200, orient=tk.HORIZONTAL, variable = self.watering_time)
        scale_watering_time.grid(column=1, row=2, ipady=20)
        scale_watering_time.set(18)

        # Cycle Time
        self.cycle_time = tk.DoubleVar()
        scale_cycle_time = tk.Scale(self.root, from_=0.0, to=60.0, length=200, orient=tk.HORIZONTAL, variable = self.cycle_time)
        scale_cycle_time.grid(column=2, row=2, ipady=20)
        scale_cycle_time.set(18)

        # Set Button
        buttonA = tk.Button(self.root, text="Set Configuration", command=self.set_config)
        buttonA.grid(column=1, row=4)
        self.root.mainloop()
    def set_config(self):
        print self.lights_on.get() # DO SOMETHING
        print self.lights_off.get() # DO SOMETHING
        print self.watering_time.get() # DO SOMETHING
         
"""
Node Class
This class is responsible for acting as the HTTP interface between the server and controller(s)
"""
class Node:
    def __init__(self, config=None):
        self.config = config
        self.threads_active = True
        self.errors = []
        if self.config['CTRL_CONF']:
            self.controller = Controller(config=self.config['CTRL_CONF'])
        else:
            self.controller = Controller(config=self.config['CTRL_CONF'], dummy=True) # use dummy if controller is disabled (i.e. for debugging)
        self.queue = [] # the outgoing queue
        threading.Thread(target=self.watchdog, args=(), kwargs={}).start()
    def watchdog(self):
        while self.threads_active == True:
            try:
                d = self.controller.parse()
                d['time'] = datetime.strftime(datetime.now(), "%Y-%m-%d %H:%M:%S") # grab the current time-stamp for the sample
                d['uid'] = self.config['UID']
                self.queue.append(d) # add the sample to the outgoing queue
            except Exception as e:
                print str(e)
                self.threads_active == False
                self.errors.append(e)
    def ping(self, d):
        try:
            r = None
            addr = self.config['SERVER_ADDR']
            r = requests.post(addr, json=d)
            return (r.status_code, r.json())
        except Exception as e:
            # print str(e)
            if r is not None:
                return (r.status_code, r.reason)
            else:
                return (400, 'Lost server')
    def run(self, queue_limit=16, error_limit=None, gui=False):
        """
        Run node as HTTP daemon
        Notes:
        * Node-App configuration is Push-Pull
        * For each iteration, the latest data gathered from the Controller is pushed from the Queue
        * Data is pushed to the App via HTTP Post to SERVER_ADDR
        * If the App has a task waiting, the task is returned as the response to the POST
        """
        if gui:
            self.gui = GUI().start()
        try:
            while ((len(self.errors) < error_limit) or (error_limit is None)) and self.threads_active:
                # Handle out-queue
                n = len(self.queue)
                if n > 0:
                    try:
                        d = self.queue.pop()
                        while len(self.queue) > queue_limit:
                            self.queue.pop(0) # grab from out-queue
                        ce = self.ping(d) # push sample to server, possibly getting task from pull
                        if ce is not None:
                            self.errors.append(ce)
                    except Exception as e:
                        print str(e)
                else:
                    d = {}
                    
                # Handle accrued responses/errors
                m = len(self.errors)
                if m > 0:
                    for e in self.errors:
                        # ERROR CODES
                        if e[0] == 200:
                            self.errors.pop()
                        if e[0] == 400:
                            self.errors.pop() #!TODO bad connection!
                        if e[0] == 500:
                            self.errors.pop() # self.errors.pop() #!TODO server there, but uncooperative!
                        if e[0] is None:
                            self.errors.pop()
                        else:
                            pass #self.errors.pop() #!TODO Unknown errors 
                # Summary
                if d != {}:
                    print "Queue: %d, Response: %s, Data: %s" % (n, str(ce), str(d['data']))
            else:
                print self.errors
        except KeyboardInterrupt:
            print "\nexiting..."
        except Exception as e:
            print str(e)
        self.threads_active = False
        exit(0)
    
if __name__ == '__main__':
    if len(sys.argv) > 1:
        configfile = sys.argv[1]
    else:
        configfile = 'default.cfg'
    with open(configfile) as jsonfile:
        config = json.loads(jsonfile.read())
    node = Node(config=config)
    #node.run() # quickstart as daemon
    node.run(gui=True) # quickstart as GUI
    
