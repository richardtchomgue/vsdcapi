import json
from datetime import datetime, date, time

from odoo import api, models, _

RECEIPT_LABELS = {'NS': 'Normal Sales',
                  'NR': 'Normal Refund',
                  'TS': 'Training Sales',
                  'TR': 'Training Refund',
                  }

SECTION_MAP = {
    'NS': '-account.zreport-1',
    'TS': '-account.zreport-2',
    'NR': '-account.zreport-3',
    'TR': '-account.zreport-4'
}


class DailyReport(models.AbstractModel):
    _inherit = 'account.report'
    _name = 'account.zreport'
    _description = 'Daily Z Report'

    filter_date = {'mode': 'range', 'filter': 'today'}
    filter_multi_company = True
    filter_unfold_all = False

    def get_invoice_line_values(self, invoice_id):
        # TODO: Substitute remaining_qty with real value and add tax % column
        query = """SELECT line.id as id,
        product.id AS product_id,
        line.name AS description,
        COALESCE(line.quantity,0) as quantity,
        0.0 as remaining_qty,
        COALESCE(line.price_unit,0.0) as unit_price,
        line.quantity * line.price_unit AS sale_amount,
        '0.0 %' as tax_percent,
        line.amount_tax AS amount_tax,
        line.price_total AS total
        FROM account_move_line AS line
        JOIN product_product AS product ON (product.id=line.product_id)
        WHERE line.move_id = '{invoice_id}'
        AND line.exclude_from_invoice_tab IS FALSE 
        """.format(invoice_id=invoice_id)
        self._cr.execute(query)
        vals_list = self._cr.dictfetchall()
        res = []
        res.append({
            'columns': [{'name': 'SKU/Product Number', 'style': 'color:red'},
                        {'name': 'Description', 'style': 'color:red'},
                        {'name': 'Qty', 'style': 'color:red'},
                        {'name': 'Remaining Qty', 'style': 'color:red'},
                        {'name': 'Unit Price', 'style': 'color:red'},
                        {'name': 'Sales Amount', 'style': 'color:red'},
                        {'name': 'Tax %', 'style': 'color:red'},
                        {'name': 'Tax Amount', 'style': 'color:red'},
                        {'name': 'Total', 'style': 'color:red'}],
            'level': 4,
            'id': 'lines-header',
            'name': 'Line Id',
            'parent_id': f"INV_{invoice_id}"
        })
        for vals in vals_list:
            line = self.env['account.move.line'].browse(vals['id'])
            vals.update({'remaining_qty': line.product_id.with_context(
                to_date=datetime.combine(date.today(), time.max)).qty_available,
                         'tax_percent': f'{line.tax_id.amount} %'})

            columns = []
            amount_cols = ['unit_price', 'sale_amount', 'amount_tax', 'total']
            for key, val in vals.items():
                if key not in ['id']:
                    if key in amount_cols:
                        columns.append({'no_format': val, 'name': self.format_value(val)})
                    else:
                        columns.append({'name': val})
            res.append({'columns': columns,
                        'level': 4,
                        'unfoldable': False,
                        'id': vals['id'],
                        'name': vals['id'],
                        'parent_id': f"INV_{invoice_id}",
                        })
        return res

    def formatted_invoice(self, options, label, vals):
        res = []
        columns = []
        amount_cols = ['taxable_a', 'taxable_b', 'taxable_c', 'taxable_d', 'amount_tax_a', 'amount_tax_b',
                       'amount_tax_c', 'amount_tax_d', 'amount_total', 'amount_tax']
        for key, val in vals.items():
            if key not in ['name', 'id']:
                if key in amount_cols:
                    columns.append({'no_format': val, 'name': self.format_value(val),'style': 'color:#006699!important'})
                else:
                    columns.append({'name': val,'style': 'color:#006699!important'})
        unfolded = f'INV_{vals["id"]}' in options.get('unfolded_lines') or options.get('unfold_all')
        res.append({'columns': columns,
                    'level': 3,
                    'unfoldable': True,
                    'unfolded': unfolded,
                    'id': f"INV_{vals['id']}",
                    'name': vals['name'],
                    'parent_id': label,
                    })
        if unfolded:
            res += self.get_invoice_line_values(vals['id'])
        return res

    def _get_one_invoice(self, options, invoice_id):
        invoice = self.env['account.move'].browse(int(invoice_id))
        if not invoice:
            return []
        vals = {
            'id': invoice_id,
            'name': f'{invoice.name}({invoice.receipt_number})',
            'receipt_number': "",
            'customer': invoice.partner_id.name,
            'invoice_date': invoice.invoice_date,
            'taxable_a': invoice.taxable_a,
            'taxable_b': invoice.taxable_b,
            'taxable_c': invoice.taxable_c,
            'taxable_d': invoice.taxable_d,
            'amount_tax': invoice.amount_tax,
            'amount_total': invoice.amount_total,
        }
        return self.formatted_invoice(options, invoice.receipt_label, vals)

    def _get_invoice_values(self, options, label, one=False):
        if one:
            return self._get_one_invoice(options, label.split("INV_")[1])
        query = """
                    SELECT
                    move.id as id,
                    move.name || '(' || move.receipt_number || ')' as name,
                    '' AS receipt_count,
                    partner.name AS customer,
                    move.invoice_date as invoice_date, 
                    COALESCE(move.taxable_a,0.0) AS taxable_a,
                    COALESCE(move.taxable_b,0.0) AS taxable_b,
                    COALESCE(move.taxable_c,0.0) AS taxable_c,
                    COALESCE(move.taxable_d,0.0) AS taxable_d,
                    COALESCE(move.amount_tax,0.0) AS amount_tax,
                    COALESCE(move.amount_total,0.0) AS amount_total
                    FROM account_move move
                    JOIN res_partner partner ON partner.id=move.partner_id
                    WHERE move.move_type IN ('out_invoice','out_refund')
                    AND move.invoice_date BETWEEN %(date_from)s AND %(date_to)s
                    AND move.company_id = %(company_id)s
                    AND move.receipt_label = %(receipt_label)s
                    ORDER BY move.receipt_number ASC
                    """
        params = {
            'date_from': options['date']['date_from'],
            'date_to': options['date']['date_to'],
            'company_id': self.env.company.id,
            'receipt_label': label
        }
        query = self.env.cr.mogrify(query, params).decode(self.env.cr.connection.encoding)
        self._cr.execute(query)
        vals_list = self._cr.dictfetchall()
        res = []
        for vals in vals_list:
            res += self.formatted_invoice(options, label, vals)
        return res

    def _finalized_values(self, vals_list, options, line_id=None):
        ordered_vals_list = []
        for k in list(RECEIPT_LABELS.keys()):
            for v in vals_list:
                if v.get('receipt_label') == k:
                    ordered_vals_list.append(v)
                    break
        vals_list = ordered_vals_list
        result = []
        if line_id:
            line = next((rec for rec in vals_list if rec.get('receipt_label') == line_id), None)
            vals_list = [line] if line else vals_list
        for vals in vals_list:
            columns = []
            amount_cols = ['taxable_a', 'taxable_b', 'taxable_c', 'taxable_d', 'amount_tax_a', 'amount_tax_b',
                           'amount_tax_c', 'amount_tax_d', 'amount_total', 'amount_tax']
            for key, val in vals.items():
                if key != 'receipt_label':
                    if key in amount_cols:
                        columns.append({'no_format': val, 'name': self.format_value(val)})
                    else:
                        columns.append({'name': val})
            label = vals['receipt_label']
            label_verbose = RECEIPT_LABELS.get(label, 'Undefined')
            unfolded = label in options.get('unfolded_lines') or options.get('unfold_all')
            result.append({'columns': columns,
                           'level': 2,
                           'unfoldable': True,
                           'unfolded': unfolded,
                           'id': label,
                           'name': label_verbose
                           })
            if unfolded:
                result += self._get_invoice_values(options, label)
        return result

    @api.model
    def _get_report_values(self, options, line_id=None):
        query = """
            SELECT
            receipt_label,
            COUNT(receipt_label) AS receipt_count,
            '' AS customer,
            '' AS invoice_date,
            COALESCE(SUM(taxable_a),0) AS taxable_a,
            COALESCE(SUM(taxable_b),0) AS taxable_b,
            COALESCE(SUM(taxable_c),0) As taxable_c,
            COALESCE(SUM(taxable_d),0) AS taxable_d,
            COALESCE(SUM(amount_tax),0) AS amount_tax,
            COALESCE(SUM(amount_total),0) AS amount_total 
            FROM account_move
            WHERE move_type IN ('out_invoice','out_refund')
            AND invoice_date BETWEEN %(date_from)s AND %(date_to)s
            AND company_id = %(company_id)s
            GROUP BY receipt_label
            """
        params = {
            'date_from': options['date']['date_from'],
            'date_to': options['date']['date_to'],
            'company_id': self.env.company.id
        }
        query = self.env.cr.mogrify(query, params).decode(self.env.cr.connection.encoding)
        self._cr.execute(query)
        if not line_id or line_id in RECEIPT_LABELS:
            result = self._finalized_values(self._cr.dictfetchall(), options, line_id)
        else:
            result = self._get_invoice_values(options, line_id, one=True)
        return result

    def _get_columns_name(self, options):
        columns_header = [{'style': 'width:100%'},
                          {'name': 'Receipt Count'},
                          {'name': 'Customer'},
                          {'name': 'Date'},
                          {'name': 'Taxable A', 'class': 'number'},
                          {'name': 'Taxable B', 'class': 'number'},
                          {'name': 'Taxable C', 'class': 'number'},
                          {'name': 'Taxable D', 'class': 'number'},
                          {'name': 'Total Tax', 'class': 'number'},
                          {'name': 'Total Amount', 'class': 'number'},
                          ]

        return columns_header

    def get_extra_info(self, options):
        vals = {
            'MRC': self.env.user.mrc or '',
            'TIN': self.env.company.vat or '',
        }
        header_info = [f'<strong>{k}</strong>:{v}' for k, v in vals.items()]
        date_from = options['date']['date_from']
        date_to = options['date']['date_to']
        date_time = date_to + " 23:59:59"
        posted_query = """SELECT id FROM account_move 
        WHERE move_type IN ('out_invoice', 'out_refund') 
        AND invoice_date BETWEEN '{date_from}' AND '{date_to}' 
        AND company_id = '{company_id}'""".format(
            date_from=date_from, date_to=date_to, company_id=self.env.company.id)
        draft_query = """
        SELECT id FROM account_move 
        WHERE move_type IN ('out_invoice') 
        AND create_date <= '{date_time}' 
        AND company_id = '{company_id}'
        AND training = False
        AND (invoice_date > '{date}' OR invoice_date IS NULL)
        """.format(date=date_to, date_time=date_time, company_id=self.env.company.id)
        self._cr.execute(posted_query)
        posted_ids = [rec['id'] for rec in self._cr.dictfetchall()]
        self._cr.execute(draft_query)
        draft_ids = [rec['id'] for rec in self._cr.dictfetchall()]
        posted_invoices = self.env['account.move'].browse(posted_ids)
        normal_invoices = posted_invoices.filtered(lambda inv: not inv.training)
        sales_invoices = normal_invoices.filtered(lambda inv: inv.move_type == 'out_invoice')
        draft_invoices_count = len(draft_ids)
        total_items_sold = len(
            sales_invoices.mapped('invoice_line_ids').filtered(lambda l: l.product_id.type in ('product', 'consu')))
        payment_amounts = {'Normal Sales': {}, 'Normal Refund': {}}
        for invoice in normal_invoices:
            label = RECEIPT_LABELS[invoice.receipt_label]
            payment_info = []
            payments_widget = json.loads(invoice.invoice_payments_widget)
            if payments_widget:
                payment_info = payments_widget.get('content', [])
            for info in payment_info:
                key = info.get('pos_payment_name') or info.get('journal_name')
                if invoice.reversed_entry_id or invoice.reversal_move_id:
                    key = 'Cash'
                to_add = payment_amounts[label].get(key, 0)
                payment_amounts[label].update({key: abs(info['amount']) + to_add})
            if invoice.amount_residual:
                acc_amt = payment_amounts[label].get('Amount Due', 0)
                payment_amounts[label].update({'Amount Due': acc_amt + invoice.amount_residual})
        footer_info = {
            'total_items_sold': total_items_sold,
            'incomplete_sales': draft_invoices_count
        }
        sales_amounts = {
            key: "&nbsp;&nbsp;".join([f'<strong>{k}</strong>:{self.format_value(v)}' for k, v in vals.items()]) for
            key, vals
            in payment_amounts.items() if vals}
        footer_info.update({'sales_amounts': sales_amounts})
        return {
            "header_info": "&nbsp;&nbsp;&nbsp;".join(header_info),
            "footer_info": footer_info
        }

    @api.model
    def _get_lines(self, options, line_id=None):
        values = self._get_report_values(options, line_id)
        return values

    def _get_html_render_values(self, options, report_manager):
        values = super()._get_html_render_values(options, report_manager)
        values.update(self.get_extra_info(options))
        return values

    def _get_report_name(self):
        return _('Daily Z Report')

    def _get_templates(self):
        templates = super()._get_templates()
        templates['main_template'] = 'vsdc_connector.main_template'
        templates['main_table_header_template'] = 'vsdc_connector.main_table_header'
        return templates
