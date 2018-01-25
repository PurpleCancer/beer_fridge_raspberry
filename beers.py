import I2C_LCD_driver
from time import *
from threading import *
import requests
import json

mylcd = I2C_LCD_driver.lcd()
server_address = '192.168.0.12'

class PID:
    """
    Discrete PID control
    """

    def __init__(self, P=2.0, I=0.0, D=1.0, Derivator=0, Integrator=0, Integrator_max=500, Integrator_min=-500):

        self.Kp=P
        self.Ki=I
        self.Kd=D
        self.Derivator=Derivator
        self.Integrator=Integrator
        self.Integrator_max=Integrator_max
        self.Integrator_min=Integrator_min

        self.set_point=0.0
        self.error=0.0

    def update(self,current_value):
        """
        Calculate PID output value for given reference input and feedback
        """

        self.error = self.set_point - current_value

        self.P_value = self.Kp * self.error
        self.D_value = self.Kd * ( self.error - self.Derivator)
        self.Derivator = self.error

        self.Integrator = self.Integrator + self.error

        if self.Integrator > self.Integrator_max:
            self.Integrator = self.Integrator_max
        elif self.Integrator < self.Integrator_min:
            self.Integrator = self.Integrator_min

        self.I_value = self.Integrator * self.Ki

        PID = self.P_value + self.I_value + self.D_value

        if PID < -100.0:
            self.P_value *= (100/PID)
            self.I_value *= (100/PID)
            self.D_value *= (100/PID)
            return -100.0
        else:
            return max(PID, -100)

    def setPoint(self,set_point):
        """
        Initilize the setpoint of PID
        """
        self.set_point = set_point
        self.Integrator=0
        self.Derivator=0

    def setIntegrator(self, Integrator):
        self.Integrator = Integrator

    def setDerivator(self, Derivator):
        self.Derivator = Derivator

    def setKp(self,P):
        self.Kp=P

    def setKi(self,I):
        self.Ki=I

    def setKd(self,D):
        self.Kd=D

    def getPoint(self):
        return self.set_point

    def getError(self):
        return self.error

    def getIntegrator(self):
        return self.Integrator

    def getDerivator(self):
        return self.Derivator

class display_stuff (Thread):
    def __init__(self, beer_dict):
        Thread.__init__(self)
        self.beer_dict = beer_dict

    def run(self):
        for beer_id, beer in self.beer_dict.items():
            first_line = str(beer_id) + ' ' + beer.style[:9] + ' t:' + \
                         str(beer.target_temp)
            second_line = 'c:' + str(beer.current_temp)[:4] + ' r:' + \
                          str(beer.pid_val)

            print(first_line)
            print(second_line)
            mylcd.lcd_clear()
            mylcd.lcd_display_string(first_line, 1)
            mylcd.lcd_display_string(second_line, 2)
            sleep(2)
        
        

class beer_info:
    def __init__(self, beer_id, style, target_temp):
        self.beer_id = beer_id
        self.style = style
        self.target_temp = target_temp
        self.pid = PID(7.0, 0.3, 1.2)
        self.pid.setPoint(target_temp)

    def update_target(self, target_temp):
        if target_temp != self.target_temp:
            self.target_temp = target_temp
            self.pid.setPoint = target_temp

    def update_current(self, current_temp):
        self.current_temp = current_temp
        self.pid_val = 0
        if (self.target_temp <= current_temp):
            self.pid_val = self.pid.update(current_temp)

    def get_current(self):
        return self.current_temp
            

# get no of beers from server
r = requests.get('http://' + server_address + ':8000/api/v1/fridge_shelves')
beers_no = len(r.json())
#print(beers_no)

beer_dict = dict()
  

thread = display_stuff(dict())
thread.start()

while(True):
    # get info from server

    f = open('/sys/bus/w1/devices/28-0416857b1aff/w1_slave', 'r')
    content = f.read()
    f.close()

    correct_read = content.find('YES')
    if correct_read != -1:
        t_index = content.find('t=')
        current = content[t_index+2:t_index+7]
    else:
        current = 10

    # update beer info
    r = requests.get('http://' + server_address + ':8000/api/v1/fridge_shelves')
    server_json = r.json()
    content = '[{"id": "0", "style": "IPA", "target_temp": "22"}, \
                {"id": "1", "style": "Porter", "target_temp": "25"}]'
    raw_json = json.loads(content)
    beer_json = {int(el["id"]): el for el in server_json}
    #print(beer_json)
    #print(server_json)

    for i in beer_json:
        if i in beer_json:
            if i in beer_dict:
                beer_dict[i].update_target(float(beer_json[i]['beer_info'] \
                                         ['type_info']['serving_temperature']))
            else:
                beer_dict[i] = beer_info(int(i), beer_json[i]['beer_info'] \
                                         ['type_info']['name'],
                                         float(beer_json[i]['beer_info'] \
                                         ['type_info']['serving_temperature']))
        else:
            if i in beer_dict:
                del beer_dict[i]

    # update pids
    beer_pids = dict()
    for beer_id, beer in beer_dict.items():
        beer.update_current(float(current)/1000)

    # send currents to server
    for i in beer_json:
        r = requests.patch('http://' + server_address +
                           ':8000/api/v1/fridge_shelves/' + str(i) + '/',
                       json = {'id': i,
                               'current_temperature': beer_dict[i].current_temp})

    # set up thread to display data
    new_thread = display_stuff(beer_dict)
    thread.join()
    new_thread.start()
    thread = new_thread
