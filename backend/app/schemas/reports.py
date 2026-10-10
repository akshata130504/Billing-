"""Request/response schemas for /reports."""
from typing import Dict, List, Optional

from pydantic import BaseModel

from backend.app.schemas.common_refs import CustomerRef


class CurrencyScopedReport(BaseModel):
    # Every money figure in the response is in `currency` (default: the organization's
    # base currency); `currencies` lists every currency the organization has invoices or
    # payments in. Amounts in different currencies are never added together.
    currency: str
    currencies: List[str] = []


class CurrencyKPIs(BaseModel):
    currency: str
    total_revenue: str
    net_revenue: str
    total_invoiced: str
    total_collected: str
    outstanding_receivables: str
    overdue_receivables: str
    collection_rate: Optional[str] = None
    average_invoice_value: Optional[str] = None
    invoice_count: int = 0


class ReportKPIs(CurrencyScopedReport):
    total_revenue: str
    net_revenue: str
    total_invoiced: str
    total_collected: str
    outstanding_receivables: str
    overdue_receivables: str
    collection_rate: Optional[str] = None
    average_invoice_value: Optional[str] = None
    invoice_count: int = 0
    # The same KPIs for every currency (base first).
    by_currency: List[CurrencyKPIs] = []


class TimeSeriesPoint(BaseModel):
    period: str
    amount: str


class InvoicedVsCollectedPoint(BaseModel):
    period: str
    invoiced: str
    collected: str


class CollectionRatePoint(BaseModel):
    period: str
    rate: Optional[str] = None


class CustomerAmount(BaseModel):
    customer: CustomerRef
    amount: str
    currency: str


class NamedAmount(BaseModel):
    id: str
    name: str
    revenue: str
    quantity: str
    currency: str


class RevenueAnalyticsOut(CurrencyScopedReport):
    granularity: str
    revenue_over_time: List[TimeSeriesPoint]
    invoiced_vs_collected: List[InvoicedVsCollectedPoint]
    revenue_by_customer: List[CustomerAmount]
    revenue_by_product: List[NamedAmount]
    revenue_by_plan: List[NamedAmount]


class AgingBucketOut(BaseModel):
    bucket: str
    count: int
    amount: str


class ReceivablesAnalyticsOut(CurrencyScopedReport):
    outstanding_by_aging: List[AgingBucketOut]
    overdue_by_due_period: List[TimeSeriesPoint]
    collection_rate_trend: List[CollectionRatePoint]
    top_customers_by_outstanding: List[CustomerAmount]
    average_days_to_payment: Optional[float] = None


class InvoiceStatusBreakdown(BaseModel):
    count: int
    amount: str


class InvoiceAnalyticsOut(CurrencyScopedReport):
    by_status: Dict[str, InvoiceStatusBreakdown]
    total_count: int
    average_invoice_amount: Optional[str] = None


class MethodAmount(BaseModel):
    method: str
    amount: str
    currency: str


class PaymentAnalyticsOut(CurrencyScopedReport):
    total_payments: str
    payment_count: int
    method_breakdown: List[MethodAmount]
    trend: List[TimeSeriesPoint]
    refund_amount: str
    net_collected: str


class CustomerAnalyticsOut(CurrencyScopedReport):
    total_customers: int
    active_customers: int
    customers_with_outstanding_balance: int
    top_customers_by_revenue: List[CustomerAmount]
    top_customers_by_outstanding: List[CustomerAmount]


class PricingModelAmount(BaseModel):
    pricing_model: str
    amount: str
    currency: str


class QuantitySold(BaseModel):
    id: str
    name: str
    quantity: str


class ProductAnalyticsOut(CurrencyScopedReport):
    best_selling: List[NamedAmount]
    revenue_by_offering: List[NamedAmount]
    revenue_by_pricing_model: List[PricingModelAmount]
    plan_revenue: List[NamedAmount]
    quantity_sold: List[QuantitySold]
