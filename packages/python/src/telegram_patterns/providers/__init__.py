"""Optional SDK-free payment adapters; importing this module performs no I/O."""

from .cryptopay import CryptoPayAdapter
from .http import (
    InvoiceRequest,
    ProviderHttpRequest,
    ProviderHttpResponse,
    ProviderInvoice,
    ProviderNotification,
    ProviderRateLimited,
    ProviderReadFailure,
    ProviderRefund,
    ProviderWriteUnknown,
    RefundRequest,
    binding_reference,
)
from .platega import PlategaAdapter, PlategaRefundSupport
from .yookassa import YooKassaAdapter, YooKassaCreateOptions, YooKassaPeerPolicy

__all__ = [
    'CryptoPayAdapter',
    'InvoiceRequest',
    'PlategaAdapter',
    'PlategaRefundSupport',
    'ProviderHttpRequest',
    'ProviderHttpResponse',
    'ProviderInvoice',
    'ProviderNotification',
    'ProviderRateLimited',
    'ProviderReadFailure',
    'ProviderRefund',
    'ProviderWriteUnknown',
    'RefundRequest',
    'YooKassaAdapter',
    'YooKassaCreateOptions',
    'YooKassaPeerPolicy',
    'binding_reference',
]
