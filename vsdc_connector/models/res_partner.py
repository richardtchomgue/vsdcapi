import json
import logging
from pprint import pprint

import requests

from odoo import models, fields, api
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class ProductMapping(models.Model):
    _name = 'product.mapping'
    _description = 'Partner Product Mapping'

    partner_id = fields.Many2one('res.partner', required=True)
    partner_code = fields.Char(help="Partner's product code", required=True)
    product_id = fields.Many2one('product.product', string="Product", required=True)


class ResPartner(models.Model):
    _inherit = "res.partner"

    sdc_id = fields.Char(string="SDC ID")
    mrc = fields.Char(string="MRC", unique=True)
    product_mapping_ids = fields.One2many('product.mapping', 'partner_id')
    tax_payer_status = fields.Selection([('A', 'Active'), ('D', 'Discard')], string="Tax Payer Status")
    location = fields.Char(string="Location")
    synced_date = fields.Datetime(help="The date at which the data is synced with VSDC", string="Synced with VSDC at")
    date_sent = fields.Text()
    response = fields.Text()

    def write(self, vals):
        if 'vat' in vals and self.vat != vals['vat']:
            res = super(ResPartner, self).write(vals)
            self.get_customer_details()
        else:
            res = super(ResPartner, self).write(vals)
        return res

    def sync_customer_with_vsdc(self, data=None):
        partner_exists = self.sudo().search([('vat', '=', self.vat)])
        if len(partner_exists) == 1:
            headers = {"Content-Type": 'application/json'}
            custNo = self.env['ir.sequence'].next_by_code('res.partner')
            data = json.dumps({
                "tin": self.env.company.vat,
                "bhfId": self.env.company.branch_id,
                "custNo": custNo,
                "custTin": self.vat,
                "custNm": self.name,
                "adrs": self.contact_address,
                "telNo": self.phone or None,
                "email": self.email or None,
                "faxNo": None,
                "useYn": "Y",
                "remark": None,
                "regrNm": self.env.user.name,
                "regrId": self.env.user.id,
                "modrNm": self.env.user.name,
                "modrId": self.env.user.id
            })
            if not self.env.company.sdc_base_url:
                raise ValidationError("Please do the configuration setup in company.")
            url = f"{self.env.company.sdc_base_url}/branches/saveBrancheCustomers"
            try:
                self.date_sent = data
                response = requests.post(url, data=data, headers=headers, verify=False)
                if response.status_code == 200:
                    pprint(response.json())
                    json_response = response.json()
                    self.response = json_response
                    if json_response.get('resultCd', '') == '000':
                        self.synced_date = fields.Datetime.now()
                        self.message_post(body="Partner successfully synced with VSDC")
                        return True

            except Exception as e:
                raise ValidationError(f"Something went wrong with your request: {e}")

    @api.model
    def create(self, vals):
        partner = super(ResPartner, self).create(vals)
        return partner

    @api.model
    def pos_get_customer_details(self, vat=None, is_pos_request=None):
        return self.get_customer_details(vat=vat, is_pos_request=is_pos_request)

    def get_customer_details(self, vat=None, is_pos_request=None):
        vat = vat if is_pos_request else self.vat
        if not self.env.company.sdc_base_url or not vat or not self.env.company.branch_id:
            return {
                "successful": False,
                "payload": 'Please provide the auth details for VSDC!'
            }
        headers = {"Content-Type": 'application/json'}
        data = json.dumps({"tin": self.env.company.vat, "bhfId": self.env.company.branch_id, "custmTin": vat})
        if not self.env.company.sdc_base_url:
            raise ValidationError("Please do the configuration setup in company.")
        url = f"{self.env.company.sdc_base_url}/customers/selectCustomer"
        try:
            response = requests.post(url, data=data, headers=headers, verify=False)
            if response.status_code == 200:
                pprint(response.json())
                json_response = response.json()
                if json_response.get('resultCd', '') == '000':
                    json_data = json_response.get('data', {})
                    json_cust_list = json_data.get('custList', [])
                    if json_cust_list:
                        customer_details = dict()
                        for customer in json_cust_list:
                            country_id = self.env['res.country'].sudo().search([('code', '=', 'RW')])
                            customer_details = {
                                'name': customer.get('taxprNm', ''),
                                'location': customer.get('locDesc', ''),
                                'tax_payer_status': customer.get('taxprSttsCd', ''),
                                'street': customer.get('sctrNm', ''),
                                'street2': customer.get('dstrtNm', ''),
                                'city': customer.get('prvncNm', ''),
                                'country_id': country_id.id or False,
                                'company_type': 'company',
                            }
                        if customer_details and not is_pos_request:
                            self.sudo().write(customer_details)
                            self.sync_customer_with_vsdc()
                        else:
                            return {
                                "successful": True,
                                "payload": customer_details
                            }
                if not is_pos_request:
                    return
                else:
                    return {
                        "successful": False,
                        "payload": json_response.get('resultMsg', '')
                    }

        except Exception as e:
            if not is_pos_request:
                return
            else:
                return {
                    "successful": False,
                    "payload": e
                }

    @api.model
    def create_from_ui(self, partner):
        res = super(ResPartner, self).create_from_ui(partner)
        partner_id = self.sudo().browse(res)
        if partner_id and partner_id.vat:
            partner_id.sync_customer_with_vsdc()
        return res

