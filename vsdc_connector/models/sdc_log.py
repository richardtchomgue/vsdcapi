import logging

from odoo import api, fields, models
from .utils import success_response

RESPONSE_TYPES = [('error', 'Error'), ('success', 'Success')]

_logger = logging.getLogger(__name__)

class VSDCResponse(models.Model):
    _name = 'sdc.response'
    _description = "VSDC Response"


class VSDCLog(models.Model):
    _name = 'sdc.log'
    _description = "VSDC Log"

    company_id = fields.Many2one('res.company', required=True, string="Company")
    sid = fields.Char(required=True, string="SID")
    type = fields.Selection(RESPONSE_TYPES, required=True)
    time = fields.Datetime(default=fields.Datetime.now())
    description = fields.Char(required=True)

    @api.model
    def get_or_create(self, company, sid, res, dt=fields.Datetime.now()):
        _logger.info(f"Creating SDC Log: {company.name} {sid.upper()} {res} {dt}")
        sid = sid.upper()
        _type = 'success'
        msg = res
        if isinstance(res, dict):
            if res.get('resultCd') != '000':
                _type = 'error'
            msg = res.get('resultMsg', "")

        rec = self.env['sdc.log'].sudo().search([('company_id', '=', company.id), ('sid', '=', sid), ('type', '=', _type)])
        if rec.exists():
            rec.write({'description': msg, 'time': dt})
        else:
            self.env['sdc.log'].sudo().create({'company_id': company.id, 'sid': sid, 'type': _type, 'description': msg})
