# -*- coding: utf-8 -*-

{
    'name': 'Yotta Pay Payment Acquirer',
    'category': 'Accounting/Payment Acquirers',
    'summary': 'Payment Acquirer: Yotta Pay Implementation',
    'version': '1.0',
    'description': """Yotta Pay Payment Acquirer""",
    'author': 'Yotta Digital Ltd',
    'maintainer': 'Yotta Digital Ltd',
    'website': 'https://yottapay.co.uk',
    'license': 'GPL-3',
    'images': [
        'static/description/banner.png'
    ],
    'depends': ['payment'],
    'data': [
        'views/payment_views.xml',
        'views/payment_yottapay_templates.xml',
        'data/payment_acquirer_data.xml',
    ],
    'installable': True,
    'application': True,
    'post_init_hook': 'create_missing_journal_for_acquirers',
    'uninstall_hook': 'uninstall_hook'
}
