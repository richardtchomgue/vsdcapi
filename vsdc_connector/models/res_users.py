import json
import logging

import pytz
import requests
from pprint import pprint
import unicodedata

from odoo import models, fields, api
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)
tz = pytz.timezone("Africa/Kigali")


class ResUser(models.Model):
    _inherit = 'res.users'

    synced_date = fields.Datetime(help="The date at which the data is synced with VSDC", string="Synced with VSDC at")
    response = fields.Text()
    data_sent = fields.Text()

    @api.model
    def create(self, vals):
        res = super(ResUser, self).create(vals)
        if res:
            synced = res.sync_user_with_vsdc()
            if synced:
                res.synced_date = fields.Datetime.now()
        return res

    def action_sync_user_with_vsdc(self):
        self.sync_user_with_vsdc()

    def sync_user_with_vsdc(self):
        headers = {"Content-Type": 'application/json'}
        name = ''.join(c for c in unicodedata.normalize('NFD', self.name)
                  if unicodedata.category(c) != 'Mn')
        data = json.dumps({
            "tin": self.env.company.vat,
            "bhfId": self.env.company.branch_id,
            "userId": self.id,
            "userNm": name,
            "pwd": '12341234',
            "adrs": self.partner_id.contact_address,
            "cntc": self.partner_id.phone,
            "authCd": None,
            "remark": None,
            "useYn": "Y",
            "regrNm": self.env.user.name,
            "regrId": self.env.user.id,
            "modrNm": self.env.user.name,
            "modrId": self.env.user.id
        })
        self.data_sent = data
        if not self.env.company.sdc_base_url:
            raise ValidationError("URL not found! Please do the configuration setup in company.")
        url = f"{self.env.company.sdc_base_url}/branches/saveBrancheUsers"
        try:
            response = requests.post(url, data=data, headers=headers, verify=False)
            if response.status_code == 200:
                pprint(response.json())
                json_response = response.json()
                self.response = json_response
                if json_response.get('resultCd', '') == '000':
                    self.synced_date = fields.Datetime.now()
                    return True
        except Exception as e:
            raise ValidationError(f"Something went wrong with your request: {e}")
