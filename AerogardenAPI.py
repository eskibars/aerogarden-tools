import urllib
import requests
import base64
import logging
import time
import re
from datetime import datetime

class AerogardenAPI():
    def __init__(self, username, password, host='http://ec2-54-86-39-88.compute-1.amazonaws.com:8080'):
        self._username = urllib.parse.quote(username)
        self._password = urllib.parse.quote(password)
        self._host = host
        self._userid = None
        self._error_msg = None
        self._data = None

        self._login_url = "/api/Admin/Login"
        self._status_url = "/api/CustomData/QueryUserDevice"
        self._update_url = "/api/Custom/UpdateDeviceConfig"

        self._headers = {
            "User-Agent" : "HA-Aerogarden/0.1",
            "Content-Type" : "application/x-www-form-urlencoded"
        }

        self.login()

    @property
    def error(self):
       return self._error_msg

    def login(self):
        post_data = "mail=" + self._username + "&userPwd=" + self._password
        url = self._host + self._login_url

        try:
            r = requests.post(url, data=post_data, headers=self._headers)
        except RequestException:
            _LOGGER.exception("Error communicating with aerogarden servers")
            return False

        response = r.json()

        userid = response["code"]
        if userid > 0:
             self._userid = str(userid)
        else:
            self._error_msg = "Login api call returned %s" % (response["code"])

    def is_valid_login(self):
        if self._userid:
            return True

        return

    def all_properties(self, macaddr):
      if macaddr not in self._data:
            return None

      return self._data[macaddr]

    def garden_property(self, macaddr, field):
        if macaddr not in self._data:
            return None

        if field not in self._data[macaddr]:
            return None

        return self._data[macaddr][field]

    def light_toggle(self, macaddr):
        if macaddr not in self._data:
            return None

        post_data = { 
            "airGuid" : macaddr, 
            "chooseGarden" : self.garden_property(macaddr, "chooseGarden"), 
            "userID" : self._userid,
            "plantConfig" :  "{ \"lightTemp\" : %d }" % (self.garden_property(macaddr, "lightTemp"))
        }
        url = self._host + self._update_url

        try:
            r = requests.post(url, data=post_data, headers=self._headers)
        except RequestException:
            _LOGGER.exception("Error communicating with aerogarden servers")
            return False

        results = r.json()

        if "code" in results:
            if results["code"] == 1:
                return True

        self._error_msg = "Didn't get code 1 from update API call: %s" % (results["msg"])
        self.update(no_throttle=True)

        return False


    @property
    def gardens(self):
        return self._data.keys()

    def convertHexToInteger(self, hexCode):
      return int(hexCode, 16)

    def convertHexToTime(self, hexTime):
      r = re.match(r'([0-9a-f]{2})([0-9a-f]{2})', hexTime)
      if r is None:
        return False
      
      hour = int(r.group(1), 16)
      minute = int(r.group(2), 16)
      now = datetime.now()
      return datetime(year=now.year, month=now.month, day=now.day, hour=hour, minute=minute)

    def update(self):
        data = {}
        if not self.is_valid_login():
            return 

        url = self._host + self._status_url
        post_data = "userID=" + self._userid

        try:
            r = requests.post(url, data=post_data, headers=self._headers)
        except RequestException:
            _LOGGER.exception("Error communicating with aerogarden servers")
            return False
        except ConnectionTimeout:
            _LOGGER.exception("Error communicating with aerogarden servers")
            return False

        garden_data = r.json()

        if "Message" in garden_data:
            self._error_msg = "Couldn't get data for garden (correct macaddr?): %s" % (garden_data["Message"])
            return False

        for garden in garden_data:
            if "plantedName" in garden:
                garden["plantedName"] = base64.b64decode(garden["plantedName"]).decode('utf-8')
            if "deviceIP" in garden:
                garden["deviceIP"] = re.sub(r'http(s?)://','',garden["deviceIP"])
            if "clock" in garden:
                garden["clock"] = self.convertHexToTime(garden["clock"])
            if "lightCycle" in garden:
                m = re.match(r'([0-9a-f]{4})([0-9a-f]{4})', garden["lightCycle"])
                if m is not None:
                  startHour = self.convertHexToTime(m.group(1))
                  endHour = self.convertHexToTime(m.group(2))
                  garden["lightCycleStart"] = startHour
                  garden["lightCycleEnd"] = endHour
            if "pumpTest" in garden:
                garden["pumpTest"] = (garden["pumpTest"] == 0)
            if "lightStat" in garden:
                garden["lightStat"] = (garden["lightStat"] == 0)
            if "pumpStat" in garden:
                garden["pumpStat"] = (garden["pumpStat"] == 0)
            if "pumpCycle" in garden:
              m = re.match(r'([0-9a-f]{4})([0-9a-f]{4})', garden["pumpCycle"])
                if m is not None:
                  garden["pumpCycleTimeOn"] = self.convertHexToInteger(m.group(1))
                  garden["pumpCycleTimeOff"] = self.convertHexToInteger(m.group(2))

            gardenmac = garden["airGuid"]
            data[gardenmac] = garden

        self._data = data
        return True
       
