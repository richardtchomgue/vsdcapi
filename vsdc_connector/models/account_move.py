import json
import logging
import re

import pytz
from datetime import datetime

from odoo import models, fields, _, api
from odoo.addons.vsdc_connector.controllers.api_calls import Messenger
from odoo.exceptions import UserError, ValidationError

from .utils import Miner

tz = pytz.timezone("Africa/Kigali")

_logger = logging.getLogger(__name__)


def camel_to_snake(st):
    return re.sub(r'(?<!^)(?=[A-Z])', '_', st).lower()


RECEIPT_LABELS = [('NS', 'Normal Sales'),
                  ('NR', 'Normal Refund'),
                  ('TS', 'Training Sales'),
                  ('TR', 'Training Refund'),
                  ('P', 'Purchases')]


class AccountMove(models.Model):
    _inherit = "account.move"

    receipt_number = fields.Integer(readonly=True, default=0, String="Receipt ID", copy=False)
    copies_count = fields.Integer(readonly=True, string="Receipt Reprint Count")
    send_purchase = fields.Char(compute="compute_send_purchase", string="Purchase data")
    send_receipt = fields.Char(compute='compute_send_receipt', string="Receipt data")
    stamps = fields.One2many('account.move.stamp', 'move_id')
    stamp = fields.Many2one('account.move.stamp', compute='compute_stamp')
    sdc_receipt_number = fields.Char(related='stamp.sdc_receipt_number')
    post_date = fields.Datetime('Posted on', default=lambda self: self.write_date or fields.Datetime.now())
    tax_amounts = fields.Binary(compute='compute_tax_amounts')

    invoice_ok = fields.Boolean(compute='compute_is_invoice', store=True)
    bill_ok = fields.Boolean(compute='compute_is_bill', store=True)
    import_ok = fields.Boolean(compute='compute_import_status', store=True)
    training = fields.Boolean(default=False)
    receipt_printed = fields.Boolean(default=False)
    invoice_printed = fields.Boolean(default=False)
    receipt_print_uid = fields.Many2one('res.users', 'Receipt Printed By')
    invoice_print_uid = fields.Many2one('res.users', 'Invoice Printed By')
    registration_type = fields.Selection([('A', 'Automatic'), ('M', 'Manual')], default='A', required=True)
    recv_invoice_id = fields.Many2one('account.move.recv', 'Supplier Invoice', ondelete='restrict')
    import_item_id = fields.Many2one('recv.import.item', 'Import Item', ondelete='restrict')
    taskCd = fields.Char(related="import_item_id.taskCd")
    factor = fields.Integer(compute='compute_factor')
    receipt_label = fields.Selection(RECEIPT_LABELS, string='Label', compute='compute_receipt_label', store=True)
    taxable_a = fields.Monetary(currency_field='currency_id', compute='compute_tax_amounts', store=True)
    taxable_b = fields.Monetary(currency_field='currency_id', compute='compute_tax_amounts', store=True)
    taxable_c = fields.Monetary(currency_field='currency_id', compute='compute_tax_amounts', store=True)
    taxable_d = fields.Monetary(currency_field='currency_id', compute='compute_tax_amounts', store=True)
    tax_rate_a = fields.Float(compute='compute_tax_amounts', store=True)
    tax_rate_b = fields.Float(compute='compute_tax_amounts', store=True)
    tax_rate_c = fields.Float(compute='compute_tax_amounts', store=True)
    tax_rate_d = fields.Float(compute='compute_tax_amounts', store=True)
    amount_tax_a = fields.Monetary(currency_field='currency_id', compute='compute_tax_amounts', store=True)
    amount_tax_b = fields.Monetary(currency_field='currency_id', compute='compute_tax_amounts', store=True)
    amount_tax_c = fields.Monetary(currency_field='currency_id', compute='compute_tax_amounts', store=True)
    amount_tax_d = fields.Monetary(currency_field='currency_id', compute='compute_tax_amounts', store=True)
    vat = fields.Char(related='partner_id.vat', store=True)
    sent_to_vsdc = fields.Boolean(default=False, string="Sent", copy=False)
    synced_date = fields.Datetime(help="The date at which the data is synced with VSDC", copy=False, string="Synced with VSDC at")
    payment_method_id = fields.Many2one('pos.payment.method', string="Payment Method", copy=False)
    reason_id = fields.Many2one('vsdc.return.reason', string="Reason", copy=False)
    send_import_item = fields.Text()
    send_purchase_response = fields.Text()
    send_receipt_response = fields.Text()
    send_import_response = fields.Text()


    @api.model
    def cron_send_to_vsdc(self):
        pass
        # self.sdc_send_invoices()
        # self.sdc_send_bills()

    @api.depends('state')
    def compute_cis_version(self):
        version_no = '15.0.1.0.0'
        module_id = self.env['ir.module.module'].sudo().search([('name', '=', 'vsdc_connector')])
        if module_id:
            version = module_id.mapped('latest_version')
            if version:
                version_no = version[0]
        self.cis_version = version_no

    @api.depends('move_type', 'training')
    def compute_receipt_label(self):
        for move in self:
            if not move.invoice_ok:
                move.receipt_label = 'P'
            if move.training:
                if 'refund' in move.move_type:
                    move.receipt_label = 'TR'
                else:
                    move.receipt_label = 'TS'
            else:
                if 'refund' in move.move_type:
                    move.receipt_label = 'NR'
                else:
                    move.receipt_label = 'NS'

    @api.onchange('registration_type')
    def onchange_registration_type(self):
        self.recv_invoice_id = False
        self.invoice_date = False
        self.taskCd = False
        for line in self.invoice_line_ids:
            if line.recv_line_id:
                line.update({'recv_line_id': False, 'quantity': 1})
            if line.import_item_id:
                line.update({'import_item_id': False, 'quantity': 1})

    @api.onchange('recv_invoice_id')
    def onchange_recv_invoice_id(self):
        if self.recv_invoice_id:
            self.invoice_date = self.recv_invoice_id.create_date
        for line in self.invoice_line_ids:
            line.update({'recv_line_id': False, 'quantity': 1})

    @api.onchange('import_item_id')
    def onchange_taskCd(self):
        for line in self.invoice_line_ids:
            line.update({'import_item_id': False, 'quantity': 1})

    def compute_factor(self):
        for move in self:
            move.factor = -1 if move.move_type == 'out_refund' else 1

    @api.depends('company_id', 'partner_id')
    def compute_import_status(self):
        for move in self:
            buyer_country = move.company_id.country_id
            seller_country = move.partner_id.country_id
            move.import_ok = (buyer_country and seller_country) and (buyer_country != seller_country)

    def mark_printed(self, ui=False):
        if ui:
            self.write({'receipt_printed': True, 'receipt_print_uid': self.env.user.id})
        else:
            self.write({'invoice_printed': True, 'invoice_print_uid': self.env.user.id})

    @api.model
    def mark_printed_from_ui(self, uid, refund=False):
        pos_orders = self.env['pos.order'].sudo().search([("pos_reference", "=ilike", f'%{uid}')])
        if pos_orders:
            moves = self.env['account.move'].sudo().browse(
                [order.account_move.id for order in pos_orders.filtered(lambda order: order.account_move)])
            if moves:
                if refund:
                    credit_notes = moves.mapped('reversal_move_id')
                    for move in credit_notes:
                        move.mark_printed(ui=True)
                else:
                    moves.mark_printed(ui=True)
        return {'code': 0, 'message': 'success'}

    @api.model
    def create(self, vals):
        res = super(AccountMove, self).create(vals)
        if res.move_type in ['out_refund', 'in_refund'] and not res.reversed_entry_id:
            raise UserError(_("You can only create a refund from an existing invoice/bill"))
        if res.reversed_entry_id:
            res.training = res.reversed_entry_id.training
        else:
            res.training = res.create_uid.training_mode
        res.receipt_printed = False
        res.invoice_printed = False
        return res

    @api.depends('invoice_line_ids')
    def compute_tax_amounts(self):
        for move in self:
            amounts = Miner().get_tax_details(move.invoice_line_ids, move.company_id, move.partner_id,
                                              move.move_type in ('out_refund', 'in_refund'))
            float_amounts = {k: float(v) for k, v in amounts.items()}
            move.taxable_a = float_amounts['totTaxablAmtA']
            move.taxable_b = float_amounts['totTaxablAmtB']
            move.taxable_c = float_amounts['totTaxablAmtC']
            move.taxable_d = float_amounts['totTaxablAmtD']
            move.tax_rate_a = float_amounts['taxRateA']
            move.tax_rate_b = float_amounts['taxRateB']
            move.tax_rate_c = float_amounts['taxRateC']
            move.tax_rate_d = float_amounts['taxRateD']
            move.amount_tax_a = float_amounts['totTaxA']
            move.amount_tax_b = float_amounts['totTaxB']
            move.amount_tax_c = float_amounts['totTaxC']
            move.amount_tax_d = float_amounts['totTaxD']
            tax_amounts = [
                ('Total A-EX', amounts['totTaxablAmtA']),
                ('Total B-18%', amounts['totTaxablAmtB']),
                ('Total Tax B', amounts['totTaxB']),
                ('Total C', amounts['totTaxablAmtC']),
                ('Total D', amounts['totTaxablAmtD']),
            ]
            move.tax_amounts = [rec for rec in tax_amounts if float(rec[1])]

    def compute_stamp(self):
        for move in self:
            move.stamp = move.stamps and move.stamps[0]

    @api.depends('move_type')
    def compute_is_invoice(self):
        for move in self:
            move.invoice_ok = move.move_type in ('out_invoice', 'out_refund')

    @api.depends('move_type')
    def compute_is_bill(self):
        for move in self:
            move.bill_ok = move.move_type == 'in_invoice'

    def get_receipt_time(self):
        self.ensure_one()
        return (self.post_date or self.write_date).astimezone(pytz.timezone('Africa/Kigali'))

    def compute_send_receipt(self):
        for invoice in self:
            invoice.send_receipt = {}
            if invoice.receipt_number:
                invoice.send_receipt = json.dumps(Miner().get_sale_receipt_data(invoice, on_confirmation=self.env.context.get('on_invoice_confirm', False)))

    def compute_send_purchase(self):
        for invoice in self:
            invoice.send_purchase = {}
            # if invoice.receipt_number:
            invoice.send_purchase = json.dumps(Miner().get_purchase_data(invoice))

    @api.model
    def sdc_send_bills(self):
        _logger.info(_(f"sending bills {self.env.user.company_ids.mapped('name')}"))
        # for company in self.env.user.company_ids.filtered(lambda com: com.sdc_base_url):
            # _logger.debug(_(f"Sending bills for {company.name}"))
            # bills = self.env['account.move'].sudo().search(
            #     [('state', '!=', 'draft'), ('bill_ok', '=', True), ('sent_to_vsdc', '=', False),
            #      ('company_id', '=', company.id), ('receipt_number', '>', 0), ('import_ok', '=', False)],
            #     order='id asc', limit=100)
        company_id = self.company_id
        if not company_id.branch_type == 'hq':
            raise ValidationError("Purchase Data must be synced between Headquarters only! Please check your branch in company settings")
        if self.state == 'draft' or not self.bill_ok:
            return
        try:
            if not self.company_id.sdc_base_url:
                raise UserError(_(f"VSDC Base URL is not configured for {self.company_id.name}"))
            purchases = self.send_purchase
            dt = fields.Datetime.now()
            res = Messenger(self.env.user, purchases, company=company_id, endpoint='trnsPurchase/savePurchases').send_purchase()
            self.send_purchase_response = res
            self.env['sdc.log'].get_or_create(self.company_id, 'send_purchase', res, dt)
            if isinstance(res, dict) and res.get('resultCd') == "000":
                self.write({'sent_to_vsdc': True, 'synced_date': fields.Datetime.now()})
                self.message_post(body="Bill successfully synced with VSDC")
            else:
                self.message_post(body=f"Sync Response\n: {res}")
                raise ValidationError(f"VSDC Response: {res}")

        except Exception as e:
            # TODO: Use logging for debugging and log the vsdc response on the invoice chatter
            self.message_post(body=f"Bill Sync Failed!\n See detailed response: {e}")
            _logger.error(f"{e}")

    def _send_invoice_to_vsdc(self):
        self.ensure_one()
        if self.state == 'draft' or not self.invoice_ok:
            return
        try:
            if not self.company_id.sdc_base_url:
                raise UserError(_(f"VSDC Base URL is not configured for {self.company_id.name}"))
            dt = fields.Datetime.now()
            res = Messenger(self.create_uid, self.with_context(on_invoice_confirm=True).send_receipt, company=self.company_id, endpoint='trnsSales/saveSales').send_receipt()
            self.send_receipt_response = res
            self.env['sdc.log'].get_or_create(self.company_id, 'send_receipt', res, dt)
            if isinstance(res, dict) and res.get('resultCd') == "000":
                self.sent_to_vsdc = True

                # Delete old stamps
                previous_stamps = self.env['account.move.stamp'].search([('move_id', '=', self.id)])
                if previous_stamps:
                    previous_stamps.unlink()

                # Save the invoice stamp
                data = res.get('data', {})
                res_date = data.get('vsdcRcptPbctDate', '')
                date_format = datetime.strptime(res_date, "%Y%m%d%H%M%S")
                date_format = date_format.astimezone(pytz.timezone('Africa/Kigali'))
                date_str = date_format.date().strftime("%d/%m/%Y")
                time_str = date_format.time().strftime("%H:%M:%S")
                stamp_data = {
                    "move_id": self.id,
                    "signature": data.get('rcptSign', ''),
                    "internal_data": data.get('intrlData', ''),
                    "r_number": data.get('rcptNo', ''),
                    "s_number": data.get('sdcId', ''),
                    "g_number": data.get('totRcptNo', ''),
                    "r_label": f"N{(self.move_type == 'out_refund' and 'R') or 'S'}",
                    "date": date_str,
                    "time": time_str,
                    "mrc_number": data.get('mrcNo', ''),
                }
                self.env['account.move.stamp'].sudo().create(stamp_data)

                # Post message in chatter
                self.message_post(body="Invoice successfully synced with VSDC")
                self.synced_date = fields.Datetime.now()

                # Update the stock in VSDC
                # if not self.inventory_sent_to_vsdc:
                #     self.update_vsdc_stock()

            else:
                self.message_post(body=f"Sync Response\n: {res}")
                raise ValidationError(f"VSDC Response: {res}")
        except Exception as e:
            self.message_post(body=f"Receipt Sync Failed!\n See detailed response: {e}")
            _logger.error(f"{e}")
            raise ValidationError(e)

    # @api.model
    # def sdc_send_invoices(self):
    #     for company in self.env.user.company_ids.filtered(lambda com: com.sdc_base_url):
    #         invoices = self.env['account.move'].sudo().search(
    #             [('state', '!=', 'draft'), ('invoice_ok', '=', True), ('stamps', '=', False),
    #              ('company_id', '=', company.id), ('receipt_number', '>', 0)], order='id asc',
    #             limit=100)
    #         for invoice in invoices:
    #             invoice._send_invoice_to_vsdc()

    def button_sdc_send_invoice(self):
        # self.sdc_send_invoices()
        self._send_invoice_to_vsdc()

    def button_sdc_send_bill(self):
        self.sdc_send_bills()

    def validate_entries(self):
        for move in self:
            if (move.bill_ok or move.invoice_ok) and not move.invoice_line_ids:
                raise UserError(_(f"Invalid entry ({move.name}). Make sure the entry contains at least 1 line"))
            # if move.invoice_ok or move.bill_ok and any(not (line.price_unit > 0 and line.quantity > 0) for line in move.invoice_line_ids):
            #         raise UserError(_(f"Inavlid Entry ({move.name}). Item price and quantity must be greater than 0"))

    def _post(self, soft=True):
        self.validate_entries()
        res = super(AccountMove, self)._post()

        # Generate receipt_number and try sending the invoices
        # but silence errors so the posting of journal entry isn't affected
        try:
            for move in self:
                if not move.receipt_number:
                    if move.invoice_ok:
                        move.receipt_number = int(
                            self.env['ir.sequence'].with_company(move.company_id).next_by_code('invoice.sequence'))
                    elif move.bill_ok:
                        if not move.import_ok:
                            move.receipt_number = int(
                                self.env['ir.sequence'].with_company(move.company_id).next_by_code('bill.sequence'))
                # update post date
                move.post_date = fields.Datetime.now()
                if move.invoice_ok:
                    move._send_invoice_to_vsdc()
                    return res
                elif move.bill_ok and not move.import_ok:
                    move.sdc_send_bills()
                    if move.bill_ok and move.recv_invoice_id:
                        move.recv_invoice_id.sudo().synchronized = True
                    return res
                elif move.import_ok:
                    mapped_items = move.invoice_line_ids.mapped('import_item_id')
                    if mapped_items:
                        self.env['recv.import.item'].sudo().browse([item.id for item in mapped_items]).write(
                            {'state': 'approved'})
        except Exception as e:
            print("An error occurred while sending invoices/Bills:", e)
            _logger.error(f"{e}")
            return res
            # raise ValidationError(e)

    def button_draft(self):
        raise UserError(_("Operation not allowed!"))


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    send_purchaseitem = fields.Binary(compute="_send_purchaseitem")
    send_receiptitem = fields.Binary(compute='_send_receiptitem')
    price_reduce = fields.Monetary(currency_field='currency_id', compute='compute_price_reduce')
    recv_line_id = fields.Many2one('account.move.line.recv', 'Supplier Invoice Line', ondelete='restrict')
    import_item_id = fields.Many2one('recv.import.item', 'Import Item', ondelete='restrict')
    amount_tax = fields.Monetary(currency_field='company_currency_id', compute='compute_tax_vals', store=True)
    tax_id = fields.Many2one('account.tax', compute='compute_tax_vals', store=True)

    @api.onchange('recv_line_id')
    def _onchange_recv_line_id(self):
        for line in self:
            if line.recv_line_id and line.recv_line_id.qty:
                line.quantity = line.recv_line_id.qty

    @api.onchange('import_item_id')
    def _onchange_import_item_id(self):
        for line in self:
            if line.import_item_id and line.import_item_id.qty:
                line.quantity = line.import_item_id.qty

    # @api.constrains('price_unit', 'quantity')
    # def zero_price_constraint(self):
    #     for line in self:
    #         if line.product_id and not (line.price_unit > 0 and line.quantity > 0):
    #             raise UserError(_(f'Invalid quantity or price on line {line.name}'))

    @api.depends('tax_ids', 'price_total')
    def compute_tax_vals(self):
        for line in self:
            line.tax_id = line.tax_ids[0].id if line.tax_ids else False
            amount = 0.0
            for tax in line.tax_ids:
                vals = tax.compute_all(price_unit=line.price_reduce, currency=line.company_currency_id,
                                       partner=line.move_id.partner_id, quantity=line.quantity,
                                       is_refund=line.move_id.move_type in ('out_refund', 'in_refund'),
                                       product=line.product_id)
                taxes = vals['taxes']
                if taxes:
                    amount += taxes[0]['amount']
            line.amount_tax = amount

    def compute_price_reduce(self):
        for line in self:
            line.price_reduce = line.price_unit * (1 - (line.discount / 100.0))

    def _send_receiptitem(self):
        for index, line in enumerate(self):
            line.send_receiptitem = {}
            if line.move_id.receipt_number:
                line.send_receiptitem = Miner().get_sale_receiptitem_data(line, index+1, on_confirmation=self.env.context.get('on_confirmation', False))

    def _send_purchaseitem(self):
        for index, line in enumerate(self):
            line.send_purchaseitem = {}
            # if line.move_id.receipt_number:
            line.send_purchaseitem = Miner().get_purchaseitem_data(line, index+1)
