# -*- coding: utf-8 -*-
from datetime import datetime
import json
import os
import re
from threading import Thread
from xml.dom import minidom

from odoo.exceptions import UserError
from odoo.http import request
from .utils import success_response, get_error_message
from .api_calls import Messenger
import pytz
from odoo import http, _
from xml.parsers.expat import ExpatError

tz = pytz.timezone('Africa/Kigali')


def get_invoice_date_and_time(invoice):
    dt = invoice.get_receipt_time().astimezone(tz)
    date = datetime.strftime(dt, '%d/%m/%Y')
    time = datetime.strftime(dt, '%H:%M:%S')
    return {"date": date, "time": time}


# def get_fake_stamp(invoice):
#     res = {
#         "RNumber": 1,
#         "SNumber": "SDC016000047",
#         "TNumber": 1,
#         "GNumber": 1,
#         "RLabel": "1/1" + ("TS" if invoice.training else "NS"),
#         "Date": "17/10/2021",
#         "Time": "11:02:08",
#         "signature": "3IUFOU4WZBHPWUAK",
#         "internalData": "TREXY3IX5JLYV3XDVCEWN2NYO4",
#         "mrc": invoice.create_uid.mrc or "",
#         "printed": invoice.receipt_printed
#     }
#
#     return {"code": 0, "stamp": res}


# def get_client_message(response):
#     try:
#         if not response:
#             return ""
#         if type(response) == dict:
#             return response["status"] == "E" and response["description"]
#         dom = minidom.parseString(response)
#         has_error = dom.getElementsByTagName('status')[0].firstChild.data == "E"
#         msg = dom.getElementsByTagName('description')[0].firstChild.data
#         return has_error and msg
#
#     except (AssertionError, ExpatError, ValueError, KeyError):
#         return False


def delete_file(path, *args):
    if os.path.isfile(path):
        os.remove(path)


def camel_to_snake(st):
    return re.sub(r'(?<!^)(?=[A-Z])', '_', st).lower()


class CisController(http.Controller):

    def invoice_to_response(self, invoice):
        stamp = invoice.stamp
        return {"RNumber": stamp.sdc_receipt_number,
                "SNumber": stamp.s_number,
                "GNumber": stamp.g_number,
                "Date": stamp.date,
                "Time": stamp.time,
                "cis_date": get_invoice_date_and_time(invoice)['date'],
                "cis_time": get_invoice_date_and_time(invoice)['time'],
                "signature": stamp.dashed_signature,
                "internalData": stamp.dashed_internal_data,
                "mrc": stamp.mrc_number or "",
                "printed": invoice.receipt_printed,
                # 'cis_version': invoice.cis_version[5:8],
                "training": invoice.training,
                'qr_data': stamp.qr_data,
                'refund': invoice.move_type == 'out_refund',
                'origin': invoice.reversed_entry_id.receipt_number if invoice.reversed_entry_id else ''
                }

    def fetch_stamp_from_vsdc(self, invoice):
        """
        In the case where somehow the invoice paved its way to the database without a stamp,
         go ahead and fetch the stamp from the VSDC.
        :param invoice: the invoice whose stamp is being fetched
        :return: Invoice stamp
        """
        # TODO: Can't fix this part as stamp retrieval api is not available
        data = {"invId": invoice.receipt_number}
        user = invoice.create_uid
        if not invoice.company_id.sdc_base_url:
            raise UserError(_(f"VSDC Base URL is not configured for company {invoice.company_id.name}"))
        try:
            data = invoice.send_receipt
            invoice._send_invoice_to_vsdc()
            response = Messenger(user, data).send_receipt()
            error = get_error_message(response)
            if error:
                return {"code": 1, "message": error}
            data = {**{'move_id': invoice.id},
                    **{camel_to_snake(k): v for k, v in response.items() if k not in ('code', 'status')}}
            stamp = request.env['account.move.stamp'].sudo().create(data)
            invoice.stamp = stamp
            return {"code": 0, "stamp": self.invoice_to_response(invoice), "client": invoice.partner_id.vat}
        except:
            pass
        return {"code": 1, "message": "Unable to connect to VSDC."}

    @http.route('/get-receipt-stamp', type='json', auth='public', website=False, csrf=False)
    def get_receipt_stamp(self, **kwargs):
        print("getting stamp")
        """
        This function is called by the POS before printing a receipt. It returns the stamp of the associated invoice
        :param kwargs:
        :return: Invoice stamp
        """
        refund = kwargs.get('refund', False)
        uid = kwargs.get("uid")
        orders = http.request.env['pos.order'].sudo().search([("pos_reference", "=ilike", f'%{uid}')])
        try:
            assert len(orders) == 1
            order = orders[0]
            invoice = order.account_move
            if not invoice:
                return {"code": 1,
                        "message": "Unable to retrieve receipt stamp. The corresponding invoice was not found"}
            if refund:
                refund_reason = kwargs.get('refund_reason')
                reason_id = False
                if refund_reason.get('id', False):
                    reason_id = request.env['vsdc.return.reason'].sudo().search(
                        [('id', '=', refund_reason.get('id', False))])
                default_vals = [{
                    'ref': _('Reversal of: %(move_name)s, %(reason)s',
                             move_name=invoice.name,
                             reason=refund_reason.get('text', '')) if refund_reason.get('text', '') else _('Reversal of: %s', invoice.name),
                    'reason_id': reason_id.id
                    }
                ]
                invoice = invoice.reversal_move_id or invoice._reverse_moves(cancel=True,
                                                                             default_values_list=default_vals)
            return {"code": 0, "stamp": self.invoice_to_response(invoice), "client": invoice.partner_id.vat}
        except AssertionError:
            return {"code": 1,
                    "message": f"Unique constrain violated. Expected exactly one order with the given pos_reference but got {len(orders)}"}
