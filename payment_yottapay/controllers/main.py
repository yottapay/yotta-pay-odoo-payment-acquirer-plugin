# -*- coding: utf-8 -*-

import json
import logging
import requests
import werkzeug
from werkzeug import urls

from odoo import http
from odoo.http import request
from odoo.addons.payment.models.payment_acquirer import ValidationError

_logger = logging.getLogger(__name__)


class YottaPayController(http.Controller):
    _payment_intent = '/payment/yottapay/create_payment_intent'
    _payment_result = '/payment/yottapay/process_payment_result'

    @http.route('/payment/yottapay/create_payment_intent', type='http', auth='public', csrf=False)
    def create_payment_intent(self, **post):    
        url_to_redirect = post['url_process_payment_intent']
        return werkzeug.utils.redirect(url_to_redirect)

    @http.route('/payment/yottapay/process_payment_result', type='json', auth='public', csrf=False)
    def process_payment_result(self, **post):
        try:            
            response_data = json.loads(request.httprequest.data)   
            request.env['payment.transaction'].sudo().form_feedback(response_data, 'yottapay')            
        finally:
            return 'OK'
    
    
