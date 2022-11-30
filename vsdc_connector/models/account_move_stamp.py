import base64
from io import BytesIO

import qrcode

from odoo import models, fields, api


class Stamp(models.Model):
    _name = 'account.move.stamp'
    _description = 'RRA invoice stamp'

    move_id = fields.Many2one('account.move', string="Invoice")
    r_number = fields.Char(string="RECEIPT NUMBER", required=True)
    s_number = fields.Char(string="SDC ID", required=True)
    g_number = fields.Integer(string="TOTAL COUNTER", required=True)

    t_number = fields.Integer(string="TYPE COUNTER")  # FIXME: Not found in API response
    r_label = fields.Char(string="RECEIPT LABEL", size=2)  # FIXME: Not found in API response

    signature = fields.Char(string="Receipt Signature")
    internal_data = fields.Char(string="Internal Data")
    date = fields.Char(string="DATE", required=True)
    time = fields.Char(string="TIME", required=True)
    mrc_number = fields.Char(string="MRC NUMBER")
    sdc_receipt_number = fields.Char(string="RECEIPT NUMBER", compute="compute_sdc_receipt_number")
    qr_data = fields.Char("Qr Data", compute='compute_qrcode')
    qr_code = fields.Binary("QR Code", compute='compute_qrcode')
    dashed_internal_data = fields.Char(compute='compute_dashed_signature')
    dashed_signature = fields.Char(compute='compute_dashed_signature')

    def compute_dashed_signature(self):
        for stamp in self:
            stamp.dashed_internal_data = '-'.join(stamp.internal_data[i:i+4] for i in range(0, len(stamp.internal_data), 4)) if stamp.internal_data else ""
            stamp.dashed_signature = '-'.join(stamp.signature[i:i+4] for i in range(0, len(stamp.signature), 4)) if stamp.signature else ""

    def compute_qrcode(self):
        for stamp in self:
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=2,
                border=1,
            )
            vals = [stamp.date.replace('/', ''), stamp.time.replace(':', ''), stamp.s_number,
                    stamp.sdc_receipt_number, stamp.dashed_internal_data, stamp.dashed_signature]
            data = '#'.join(vals)
            stamp.qr_data = data
            qr.add_data(data)
            qr.make(fit=True)
            img = qr.make_image()
            temp = BytesIO()
            img.save(temp, format="PNG")
            qr_image = base64.b64encode(temp.getvalue())
            stamp.qr_code = qr_image

    @api.depends('r_number', 'g_number', 'r_label')
    def compute_sdc_receipt_number(self):
        for stamp in self:
            stamp.sdc_receipt_number = f'{stamp.r_number}/{stamp.g_number} {stamp.r_label}'
