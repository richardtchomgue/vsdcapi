from odoo import api, fields, models, _
from odoo.addons.vsdc_connector.controllers.api_calls import Messenger
from odoo.http import request


class VSDCProductImport(models.Model):
    _name = 'vsdc.product.import'
    _description = 'VSDC Product'
    _rec_name = 'itemNm'

    def get_default_company(self):
        cookies = request.httprequest.cookies
        cid = self.env.company.id
        if cookies.get('cids'):
            cid = cookies.get('cids').split(',')[0]
        return cid

    company_id = fields.Many2one('res.company', required=True, readonly=True, default=get_default_company)
    tin = fields.Char('TIN')
    itemCd = fields.Char('Item Code')
    itemClsCd = fields.Char('Item Classification Code')
    itemTyCd = fields.Char('Item Type Code')
    itemNm = fields.Char('Item Name')
    itemStdNm = fields.Char('Item Standard Name')
    orgnNatCd = fields.Char('Origin Place Code (Nation)')
    pkgUnitCd = fields.Char('Packaging Unit Code')
    qtyUnitCd = fields.Char('Quantity Unit Code')
    taxTyCd = fields.Char('Taxation Type Code')
    btchNo = fields.Char('Batch Number')
    regBhfId = fields.Char('Regist Branch Office ID')
    bcd = fields.Char('Barcode')
    dftPrc = fields.Integer('Default Unit Price')
    grpPrcL1 = fields.Integer('Group1 Unit Price')
    grpPrcL2 = fields.Integer('Group2 Unit Price')
    grpPrcL3 = fields.Integer('Group3 Unit Price')
    grpPrcL4 = fields.Integer('Group4 Unit Price')
    grpPrcL5 = fields.Integer('Group5 Unit Price')
    addInfo = fields.Char('Add Information')
    sftyQty = fields.Integer('Safty Quantity')
    isrcAplcbYn = fields.Char('Insurance Appicable Y/N')
    rraModYn = fields.Char('RRA Modify Y/N')
    useYn = fields.Char('Used / UnUsed')

    response = fields.Html('Response')
    request = fields.Html('Request')

    @api.model
    def action_fetch_vsdc_products(self):
        cookies = request.httprequest.cookies
        company_id = self.env['res.company'].sudo()
        if cookies.get('cids'):
            cid = cookies.get('cids').split(',')[0]
            if cid:
                company_id = self.env['res.company'].sudo().search([('id', '=', cid)])
        req_data = {"tin": company_id.vat, "bhfId": company_id.vsdc_branch_id.branch_id or self.env.company.branch,
                "lastReqDt": company_id.last_request_date}
        res = Messenger(self.env.user, req_data, company=self.env.company, endpoint='items/selectItems').recv_vsdc_items()
        if isinstance(res, dict) and res.get('resultCd') == "000":
            data = res.get('data', {})
            item_list = data.get('itemList', [])
            items = []
            for item in item_list:
                item_exists = self.search([('tin', '=', item.get('tin', '')),
                                           ('itemCd', '=', item.get('itemCd', '')),
                                           ('itemClsCd', '=', item.get('itemCd', '')),
                                           ('itemTyCd', '=', item.get('itemTyCd', ''))])
                if not item_exists:
                    item['request'] = req_data
                    item['response'] = res
                    items.append(item)
            if items and isinstance(items, list):
                self.env['vsdc.product.import'].sudo().create(items)
