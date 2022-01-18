# coding: utf-8

import json
import logging
import requests
from werkzeug import urls
from odoo import api, fields, models, _
from odoo.addons.payment.models.payment_acquirer import ValidationError
from odoo.addons.payment_yottapay.controllers.main import YottaPayController
from odoo.tools.float_utils import float_compare
from openerp import http
from hashlib import sha256

_logger = logging.getLogger(__name__)

class AcquirerYottaPay(models.Model):
    _inherit = 'payment.acquirer'    

    provider = fields.Selection(selection_add=[('yottapay', 'Yotta Pay')],
                                ondelete={'yottapay': 'set default'})

    yottapay_merchant_identifier = fields.Char('Merchant Id', required_if_provider='yottapay', groups='base.group_user')
    yottapay_payment_key = fields.Char('Payment Key', required_if_provider='yottapay', groups='base.group_user')

    @api.model
    def _get_yottapay_api_url(self, environment):
        if (environment == 'enabled'):
            return 'https://prod.yottapay.co.uk/launcher/shop/paymentgateway/new'
        else:
            return 'https://sandbox.yottapay.co.uk/launcher/shop/paymentgateway/new'

    def _get_data_to_send(self, values):
        if (values['currency'].name != 'GBP'):
            error_msg = _('Yotta Pay currently works only with GBP.')
            _logger.error(error_msg)
            raise ValidationError(error_msg)
        if ('yottapayauth_notification_id' in self.env.user._fields and self.env.user.yottapayauth_notification_id):
            yotta_notification_id = self.env.user.yottapayauth_notification_id
        else:
            yotta_notification_id = ''
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        data_to_send = {
            'type': 'creation',
            'shop_transaction_identifier': values['reference'],
            'merchant_identifier': self.yottapay_merchant_identifier,
            'customer_identifier': values.get('partner_email'),
            'amount': '{:.2f}'.format(values['amount']),
            'currency': values['currency'].name,
            'url_payment_result': urls.url_join(base_url, YottaPayController._payment_result),
            'url_merchant_page_success': urls.url_join(base_url, '/payment/process'),
            'url_merchant_page_cancel': urls.url_join(base_url, '/payment/process'),
            'yotta_notification_id': yotta_notification_id,
            'signature': ''
        }
        data_to_sign = (data_to_send['shop_transaction_identifier']
                        + data_to_send['merchant_identifier']
                        + data_to_send['customer_identifier']
                        + data_to_send['amount']
                        + data_to_send['currency']
                        + data_to_send['url_payment_result']
                        + data_to_send['url_merchant_page_success']
                        + data_to_send['url_merchant_page_cancel']
                        + data_to_send['yotta_notification_id']
                        + self.yottapay_payment_key)
        signaturevalue = sha256(data_to_sign.encode('utf-8')).hexdigest()
        data_to_send['signature'] = signaturevalue
        return data_to_send

    def _provider_request(self, method, url, json=''):
        headers = {'Plugin-Version': '1.0.0'}
        resp = requests.request(method, url, headers=headers, json=json);
        if (resp.status_code != 200):
            error_msg = _('Request failed with code (%s).', resp.status_code)
            _logger.error(error_msg)
            raise
        return resp.json()
        
    def yottapay_form_generate_values(self, values):
        try:
            data_to_send = self._get_data_to_send(values)
            yottapay_api_url = self._get_yottapay_api_url(self.state)
            response = self._provider_request('POST', yottapay_api_url, data_to_send)
            if (not response.get('url_process_payment_intent') or not response.get('yottapay_transaction_identifier')):
                error_msg = _('Missing required fields in API response.')
                _logger.error(error_msg)
                raise       
            return {'url_process_payment_intent': response['url_process_payment_intent']}
        except ValidationError as e:
            raise ValidationError(e)
        except Exception as e:
            _logger.exception('Exception in yottapay_form_generate_values for transaction "%s".', values['reference'])
            raise ValidationError('Please contact the store owner to solve the problem.')

    def yottapay_get_form_action_url(self):
        self.ensure_one()
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')        
        return urls.url_join(base_url, YottaPayController._payment_intent)

class PaymentTransactionYottaPay(models.Model):
    _inherit = 'payment.transaction'
    
    def _verify_signature(self, data):
        if (not data.get('yottapay_transaction_identifier') or 
                not data.get('shop_transaction_identifier') or 
                not data.get('merchant_identifier') or 
                not data.get('customer_identifier') or 
                not data.get('amount') or 
                not data.get('currency') or 
                not data.get('response_code')):
            error_msg = _('Missing required fields in request.')
            _logger.error(error_msg)
            raise ValidationError(error_msg)
        data_to_sign = (data['yottapay_transaction_identifier']
                        + data['shop_transaction_identifier']
                        + data['merchant_identifier']
                        + data['customer_identifier']
                        + data['amount']
                        + data['currency']
                        + data['response_code']
                        + self.acquirer_id.yottapay_payment_key)
        signaturevalue = sha256(data_to_sign.encode('utf-8')).hexdigest()
        if (signaturevalue != data['signature']):
            error_msg = _('Signature is wrong.')
            _logger.error(error_msg)
            raise ValidationError(error_msg)
        return True

    def _verify_response_code(self, data):
        if (data['response_code'] == '0'):
            self._set_transaction_done()
            return True
        else:
            if (data['response_code'] == '2'):
                info_msg = _('Payment was canceled for reference %s.', data['shop_transaction_identifier'])
                _logger.info(info_msg)
                self._set_transaction_cancel()
                res = {
                    'state_message': 'Payment was canceled.'
                }
                self.write(res)
            else:                           
                warning_msg = _('Payment was failed for reference %s.', data['shop_transaction_identifier'])
                _logger.warning(warning_msg)
                self._set_transaction_error('Payment was failed.')
            return False

    @api.model
    def _yottapay_form_get_tx_from_data(self, data):
        if (not data.get('shop_transaction_identifier')):
            error_msg = _('Missing required fields in request.')
            _logger.error(error_msg)
            raise ValidationError(error_msg)
        refname = data['shop_transaction_identifier']
        tx = self.search([('reference', '=', refname)])
        if (not tx):
            error_msg = _('No transaction found for reference %s', refname)
            _logger.error(error_msg)
            raise
        elif (len(tx) > 1):
            error_msg = _('%(count)s transaction found for reference %(reference)s', count=len(tx), reference=refname)
            _logger.error(error_msg)
            raise ValidationError(error_msg)
        return tx[0]

    def _yottapay_form_get_invalid_parameters(self, data):
        invalid_parameters = []
        if (data['amount'] != '{:.2f}'.format(self.amount)):
             invalid_parameters.append(('Amount', data['amount'], '{:.2f}'.format(self.amount)))
        if (data['currency'] != self.currency_id.name):
            invalid_parameters.append(('Currency', data['currency'], self.currency_id.name))
        if (data['customer_identifier'] != self.partner_email):
            invalid_parameters.append(('Customer identifier', data['customer_identifier'], self.partner_email))
        return invalid_parameters

    def _yottapay_form_validate(self, data):    
        if (self._verify_signature(data) and self._verify_response_code(data)):
            return True 
        else:
            return False