import json
import logging
import string

import pytz
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# timezone to be used when sending a date object to the VSDC
tz = pytz.timezone('Africa/Kigali')
_logger = logging.getLogger(__name__)


def cleaned_value(s):
    s = str(s)
    return s.translate({ord(c): None for c in string.whitespace})


'''This class is the center for communicating with the VSDC. 
It has different methods which sends/request for specific data from the VSDC'''


class Messenger:
    def __init__(self, user, data=None, method='post', url=None, company=None, endpoint=None):
        self.user = user
        self.method = method
        self.company = company or user.company_id
        self.endpoint = endpoint
        self.url = url or f'{self.company.sdc_base_url}/{self.endpoint}'
        self.data = json.loads(data) if type(data) == str else data
        self.template = None

    # def get_token(self):
    #     headers = {"Content-Type": 'application/json'}
    #     data = json.dumps({"username": self.user.mrc, "password": self.user.sdc_access_key})
    #     if not self.company.sdc_base_url:
    #         return
    #     url = f"{self.company.sdc_base_url}/auth/api/token/"
    #     response = requests.post(url, data=data, headers=headers, verify=False)
    #     if response.status_code == 200:
    #         return response.json()
    #     return

    def send(self, cmd):
        _logger.info(f"Sending data to VSDC: {cmd} {json.dumps(self.data)}")
        if not self.data:
            return "No data was passed to the VSDC messenger"
        data = json.dumps(self.data)
        headers = {'Content-Type': 'application/json'}
        r = requests.request(self.method, self.url, data=data, headers=headers)
        _logger.info(f"VSDC Response for {cmd}: {r.content}")
        res = (r.status_code == 200 and r.json()) or str(r.content)
        return res

    def send_inventory(self):
        return self.send("SEND_INVENTORY")

    def send_item(self):
        return self.send("SEND_ITEM")

    def send_purchase(self):
        return self.send("SEND_PURCHASE")

    def send_receipt(self):
        return self.send("SEND_RECEIPT")

    def send_import_item(self):
        return self.send('SEND_IMPORT_ITEM')

    def recv_purchase(self):
        return self.send("RECV_PURCHASE")

    def recv_vsdc_items(self):
        return self.send("RECV_VSDC_ITMS")

    def recv_import_item(self):
        return self.send("RECV_IMPORT_ITEM")

    def recv_receipt(self):
        return self.send("RECV_RECEIPT")

    def counters_request(self):
        return self.send("COUNTERS_REQUEST")

    def signature_request(self):
        return self.send("SIGNATURE_REQUEST")

    def date_time_request(self):
        return self.send("DATE_TIME_REQUEST")

    def id_request(self):
        return self.send("ID_REQUEST")

    def send_invoice(self):
        return self.send("EJ_DATA")

    def status_request(self):
        return self.send("STATUS_REQUEST")

    def send_receiptitem(self):
        return self.send("SEND_RECEIPTITEM")

    def recv_purchaseitem(self):
        return self.send("RECV_PURCHASEITEM")
