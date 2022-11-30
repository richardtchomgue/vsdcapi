# -*- coding: utf-8 -*-

# -*- coding: utf-8 -*-

import logging
import pytz
import requests
import json


from odoo import models, fields, _, api
from odoo.exceptions import UserError, ValidationError

tz = pytz.timezone("Africa/Kigali")

_logger = logging.getLogger(__name__)


class VSDCNotice(models.Model):
    _name = "vsdc.notice"
    _description = "VSDC Notice Logs"

    name = fields.Char(string="Title")
    is_read = fields.Boolean(string="Read", copy=False)
    notice_number = fields.Char(string="Notice Number")
    content = fields.Text(string="Content")
    detail_url = fields.Char(string="Detail URL", default="http://localhost:9980/common/link/ebm/receipt/indexEbmNotice?noticeNo=42")
    registration_name = fields.Char(string="Registration Name")
    registration_date = fields.Char(string="Registration Date")
    date_sent = fields.Text()
    response = fields.Text()

    def action_message_read(self):
        self.write({'is_read': True})
        return {}

    def get_vsdc_notifications(self):
        if not self.env.company.sdc_base_url or not self.env.company.vat or not self.env.company.branch_id or not self.env.company.last_request_date:
            raise ValidationError("Please provide the auth details for VSDC!")
        headers = {"Content-Type": 'application/json'}
        data = json.dumps({"tin": self.env.company.vat, "bhfId": self.env.company.branch_id,
                           "lastReqDt": self.env.company.last_request_date})
        url = f"{self.env.company.sdc_base_url}/notices/selectNotices"
        try:
            if not self.env.company.sdc_base_url:
                raise UserError(_(f"VSDC Base URL is not configured for {self.env.company.name}"))
            response = requests.post(url, data=data, headers=headers, verify=False)
            if response.status_code == 200:
                json_response = response.json()
                if json_response.get('resultCd', '') == '000':
                    json_data = json_response.get('data', {})
                    json_class_list = json_data.get('noticeList', [])
                    if json_class_list:
                        NotificationSudo = self.env['vsdc.notification'].sudo()
                        for notice in json_class_list:
                            notification_exists = NotificationSudo.search([('name', '=', notice.get('title', '')),
                                                                           ('notice_number', '=', notice.get('noticeNo', ''))])
                            if not notification_exists:
                                notification_vals = {
                                    'name': notice.get('title', ''),
                                    'notice_number': notice.get('noticeNo', ''),
                                    'content': notice.get('cont', ''),
                                    'detail_url': notice.get('dtlUrl', ''),
                                    'registration_name': notice.get('regrNm', ''),
                                    'registration_date': notice.get('regDt', ''),
                                    'date_sent': data,
                                    'response': json_response,
                                }
                                notification_id = NotificationSudo.create(notification_vals)
                                if notification_id:
                                    notification_id._notify_admin()
        except Exception as e:
            _logger.error(f"{e}")

    def _notify_admin(self):
        """
        Notify Admin about Notification from VSDC
        """

        base_url = f'/web#view_type=form&amp;model={self._name}&amp;id={self.id:d}'

        msg = f"""
            <p>VSDC notification from <b>{self.registration_name}</b></p><br/>
            <b>[{self.notice_number or ''}]{self.name}</b><br/>
            <p>{self.content}</p><br/>
            <div class="text-center mb5"><a href="{base_url}" class="btn btn-primary">View Notification</a><br/></div>
        """

        admin = self.env.ref('base.partner_admin')
        bot = self.env.ref('base.partner_root')
        MailChannel = self.env['mail.channel']
        MailChannel.browse(MailChannel.channel_get([admin.id])['id']).message_post(
            body=_(msg),
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
            author_id=bot.id
        )
