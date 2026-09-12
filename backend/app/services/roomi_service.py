"""Roomi AI Assistant Service for Rooman Billing.

Provides intelligent, tenant-isolated, role-aware conversational billing guidance,
navigation assistance, and grounded data queries exclusively for authenticated
internal workspace members (Owner, Admin, Finance, Viewer).
"""
from __future__ import annotations

import os
import re
import uuid
from typing import Any, Dict, List, Optional
import requests
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext
from backend.app.schemas.ai import AISourceReferenceOut
from backend.app.schemas.chat import (
    RoomiChatRequest,
    RoomiChatResponse,
    RoomiNavigationHint,
)
from backend.app.services import ai_service

# ---------------------------------------------------------------------------
# Route Knowledge Graph (Precise targets)
# ---------------------------------------------------------------------------
KNOWN_ROUTES: List[Dict[str, Any]] = [
    {"name": "Dashboard", "route": "/dashboard", "patterns": [r"\bdashboard\b", r"\boverview\b", r"\bhome\b"]},
    {"name": "Invoices", "route": "/invoices", "patterns": [r"\binvoices?\b", r"\bbill(s|ing)? list\b"]},
    {"name": "Create Invoice", "route": "/invoices/new", "patterns": [r"\bcreate (an? )?invoice\b", r"\bnew invoice\b"]},
    {"name": "Quotes", "route": "/quotes", "patterns": [r"\bquotes?\b", r"\bestimates?\b", r"\bproposals?\b"]},
    {"name": "CPQ Studio", "route": "/cpq", "patterns": [r"\bcpq\b", r"\bconfigure price quote\b"]},
    {"name": "Subscriptions", "route": "/subscriptions", "patterns": [r"\bsubscriptions?\b", r"\brecurring billing\b"]},
    {"name": "Plans & Pricing", "route": "/plans-pricing", "patterns": [r"\bplans?\b", r"\bpricing\b", r"\bcatalog\b"]},
    {"name": "Trials", "route": "/trials", "patterns": [r"\btrials?\b", r"\bfree trials?\b"]},
    {"name": "Usage & Metering", "route": "/usage", "patterns": [r"\busage\b", r"\bmeter(ed|ing)?\b", r"\bconsumption\b"]},
    {"name": "Proration Planner", "route": "/proration", "patterns": [r"\bprorat(e|ion)\b", r"\bmid[- ]cycle\b"]},
    {"name": "Payments", "route": "/payments", "patterns": [r"\bpayments?\b", r"\breceipts?\b", r"\brefunds?\b"]},
    {"name": "Collections", "route": "/collections", "patterns": [r"\bcollections?\b", r"\breceivables?\b"]},
    {"name": "Dunning Management", "route": "/dunning", "patterns": [r"\bdunning\b", r"\bretry schedule\b"]},
    {"name": "Customers", "route": "/customers", "patterns": [r"\bcustomers?\b", r"\bclients?\b"]},
    {"name": "Customer Lifecycle", "route": "/customer-lifecycle", "patterns": [r"\blifecycle\b", r"\bonboarding\b"]},
    {"name": "Expenses", "route": "/expenses", "patterns": [r"\bexpenses?\b", r"\bspending\b"]},
    {"name": "Projects", "route": "/projects", "patterns": [r"\bprojects?\b"]},
    {"name": "Timesheets", "route": "/timesheets", "patterns": [r"\btimesheets?\b", r"\btime tracking\b"]},
    {"name": "Reports", "route": "/reports", "patterns": [r"\breports?\b", r"\baging\b", r"\btax report\b"]},
    {"name": "Revenue Intelligence", "route": "/revenue-intelligence", "patterns": [r"\brevenue intelligence\b", r"\bmrr\b", r"\barr\b"]},
    {"name": "AI in Billing", "route": "/ai-billing", "patterns": [r"\bai billing\b", r"\bask zia\b"]},
    {"name": "Settings", "route": "/settings", "patterns": [r"\bsettings?\b", r"\bconfig(uration)?\b"]},
    {"name": "Integrations", "route": "/settings?tab=integrations", "patterns": [r"\bintegrations?\b", r"\brazorpay keys?\b", r"\bsmtp\b"]},
    {"name": "Team Management", "route": "/settings?tab=team", "patterns": [r"\bteam\b", r"\bmembers?\b", r"\broles?\b"]},
    {"name": "Action Center", "route": "/control-center/action-center", "patterns": [r"\baction center\b", r"\balerts?\b"]},
    {"name": "Approvals", "route": "/control-center/approvals", "patterns": [r"\bapprovals?\b"]},
    {"name": "Audit Log", "route": "/control-center/audit-log", "patterns": [r"\baudit logs?\b"]},
]


def _match_route(query: str) -> Optional[RoomiNavigationHint]:
    """Finds a matching route only when explicit regex matches."""
    q = query.lower()
    for item in KNOWN_ROUTES:
        for pat in item["patterns"]:
            if re.search(pat, q):
                return RoomiNavigationHint(
                    label=item["name"],
                    route=item["route"],
                    description=f"Go to {item['name']}",
                )
    return None


# ---------------------------------------------------------------------------
# Comprehensive Domain Knowledge Base
# ---------------------------------------------------------------------------
KNOWLEDGE_TOPICS: List[Dict[str, Any]] = [
    {
        # Rooman Billing Overview / Platform
        "patterns": [
            r"how does rooman billing work",
            r"what is rooman billing",
            r"tell me about rooman billing",
            r"about rooman billing",
            r"platform overview",
            r"how does the app work",
            r"what can rooman billing do",
            r"features of rooman billing",
        ],
        "answer": (
            "**Rooman Billing** is an enterprise-grade recurring billing, subscription management, and revenue operations platform "
            "engineered for modern SaaS, IT services, and digital businesses with native **Indian GST compliance**.\n\n"
            "Key capabilities include:\n\n"
            "• **Subscriptions & Plans**: Manage recurring billing frequencies (monthly, quarterly, annual), trial periods, and automated renewal cycles.\n"
            "• **Invoicing & GST**: Create compliant tax invoices with automatic CGST, SGST, or IGST calculation, customizable number series, and instant PDF delivery.\n"
            "• **Proration & Metering**: Accurately bill mid-cycle plan changes and rate usage-based consumption with idempotent event ingestion.\n"
            "• **Payments & Dunning**: Collect payments online via **Razorpay** (UPI, cards, netbanking) or record offline transactions, backed by automated dunning for failed payment recovery.\n"
            "• **CPQ & Quotes**: Build tiered product bundles, enforce discount approval thresholds, and convert signed quotes into active subscriptions.\n"
            "• **Financial Intelligence**: Real-time revenue analytics (MRR/ARR), receivables aging reports, and customer lifecycle insights.\n\n"
            "Use the sidebar to explore any module, or ask me specific questions about setting up your billing workflows."
        ),
        "route": {"label": "Explore Dashboard", "route": "/dashboard"},
        "chips": ["How do I create an invoice?", "Explain subscriptions", "How does proration work?"],
    },
    {
        # Invoices
        "patterns": [
            r"how (do|to) create an? invoice",
            r"create (an? )?invoice",
            r"how (do )?invoices? work",
            r"invoice lifecycle",
            r"what is an? invoice",
            r"send invoice",
        ],
        "answer": (
            "In Rooman Billing, **Invoices** represent legally binding tax documents and receivables:\n\n"
            "1. **Creating an Invoice**: Go to **Revenue → Invoices** and click **+ Create Invoice**.\n"
            "2. **Customer & Items**: Select a registered customer and add products/services from your catalog. Unit prices, HSN/SAC codes, and tax rates load automatically.\n"
            "3. **GST Calculation**: Intra-state supplies automatically calculate equal **CGST + SGST**, while inter-state supplies apply **IGST**.\n"
            "4. **Status Lifecycle**: Invoices transition through **Draft** → **Sent** (issued) → **Partially Paid** → **Paid** (or **Overdue** if unpaid by due date).\n"
            "5. **PDF & Payment Links**: Invoices feature one-click downloadable PDF generation and direct payment links for clients.\n\n"
            "Ready to create an invoice?"
        ),
        "route": {"label": "Create Invoice", "route": "/invoices/new"},
        "chips": ["How to record a payment?", "Explain GST rules", "Where are quotes?"],
    },
    {
        # Subscriptions & Recurring
        "patterns": [
            r"explain subscriptions?",
            r"how (do )?subscriptions? work",
            r"what is a subscription",
            r"recurring billing",
            r"subscription lifecycle",
            r"renewal",
        ],
        "answer": (
            "**Subscriptions** automate recurring billing for your customers over time:\n\n"
            "• **Billing Cycles**: Configure intervals such as monthly, quarterly, semi-annual, or annual renewals.\n"
            "• **Automated Invoicing**: At each cycle boundary, Rooman Billing's scheduler generates renewal invoices automatically.\n"
            "• **Status Management**: Subscriptions can be **Active**, in **Trial**, **Paused**, **Past Due** (during dunning), or **Cancelled**.\n"
            "• **Add-ons & Multi-items**: Attach recurring add-ons, seat licenses, or metered consumption components to a single subscription.\n"
            "• **Upgrades & Downgrades**: Adjust plan tiers seamlessly with automated proration adjustments.\n\n"
            "You can manage customer subscriptions under **Subscriptions → All Subscriptions**."
        ),
        "route": {"label": "View Subscriptions", "route": "/subscriptions"},
        "chips": ["How does proration work?", "What is trial management?", "What is dunning?"],
    },
    {
        # Proration
        "patterns": [
            r"what is proration",
            r"how does proration work",
            r"explain proration",
            r"prorate",
            r"mid[- ]cycle",
        ],
        "answer": (
            "**Proration** calculates proportional charges when a subscription is modified partway through an active billing cycle.\n\n"
            "For example:\n"
            "• If a customer upgrades from a ₹1,000/mo plan to a ₹2,000/mo plan exactly halfway through the month (day 15 of 30):\n"
            "  1. Rooman Billing credits the unused ₹500 from the old plan.\n"
            "  2. Calculates the remaining 15 days on the new plan (₹1,000).\n"
            "  3. Generates an immediate net adjustment invoice for ₹500 (or defers it to the next renewal cycle).\n\n"
            "You can preview and simulate proration calculations in **Subscriptions → Proration**."
        ),
        "route": {"label": "Proration Planner", "route": "/proration"},
        "chips": ["Explain subscriptions", "How to create an invoice?", "Show me reports"],
    },
    {
        # Metered Billing / Usage
        "patterns": [
            r"what is metered billing",
            r"how does metered billing work",
            r"explain meter(ed|ing)?",
            r"usage metering",
            r"consumption billing",
        ],
        "answer": (
            "**Metered Billing** allows you to bill customers dynamically based on actual usage events rather than flat tiers:\n\n"
            "• **Define Meters**: Set up meters with custom units (e.g., API requests, compute hours, storage gigabytes, active users).\n"
            "• **Aggregation Types**: Choose how events roll up:\n"
            "  - **SUM**: Totals all event quantities across the period (e.g., total API calls).\n"
            "  - **MAX**: Takes the peak usage recorded during the cycle (e.g., peak concurrent users).\n"
            "  - **LAST**: Uses the final value reported (e.g., end-of-month disk storage).\n"
            "  - **COUNT**: Counts the number of occurrences.\n"
            "• **Idempotent Ingestion**: Ingest usage events via API or CSV batch import using idempotency keys to prevent duplicate billing.\n"
            "• **Finalization**: At cycle end, consumption is rated against tier pricing and billed as an invoice line item."
        ),
        "route": {"label": "Usage & Metering", "route": "/usage"},
        "chips": ["How does proration work?", "Create an invoice", "Where are plans and pricing?"],
    },
    {
        # Dunning & Failed Payments
        "patterns": [
            r"what is dunning",
            r"how does dunning work",
            r"explain dunning",
            r"failed payments?",
            r"payment recovery",
            r"grace period",
        ],
        "answer": (
            "**Dunning Management** automates the recovery of overdue receivables and failed recurring card charges:\n\n"
            "• **Smart Retry Schedules**: Automatically retries failed transactions over configurable intervals (e.g., after 3, 7, and 14 days).\n"
            "• **Grace Periods**: Keeps the customer's service active while notifying them to resolve payment issues.\n"
            "• **Automated Notifications**: Dispatches branded email reminders with direct payment links.\n"
            "• **Terminal Actions**: If all retries fail, Rooman Billing automatically marks the invoice overdue and can pause or cancel the subscription.\n\n"
            "You can configure dunning policies in **Subscriptions → Dunning** and monitor overdue accounts in **Revenue → Collections**."
        ),
        "route": {"label": "Dunning Management", "route": "/dunning"},
        "chips": ["Where do I view collections?", "How to record a payment?", "What is CPQ?"],
    },
    {
        # GST & Taxes
        "patterns": [
            r"how does gst work",
            r"explain gst",
            r"tax(es)? calculation",
            r"cgst",
            r"sgst",
            r"igst",
            r"hsn",
            r"sac",
        ],
        "answer": (
            "Rooman Billing provides built-in **Indian Goods & Services Tax (GST)** compliance:\n\n"
            "• **Intra-state Supply**: When the customer's state matches your organization's registered state, tax is equally split into **CGST** and **SGST** (e.g., 9% + 9% for 18% GST).\n"
            "• **Inter-state Supply**: When the customer is located in a different state, the full tax is applied as **IGST** (18%).\n"
            "• **HSN/SAC Codes**: Required 4–8 digit Harmonized System / Services Accounting codes assigned to each product or service.\n"
            "• **GSTIN Validation**: Customer and organization GSTINs are verified and printed on tax invoices.\n\n"
            "Configure your state, legal name, and GSTIN under **Settings → Organization**."
        ),
        "route": {"label": "Organization Settings", "route": "/settings"},
        "chips": ["How do I create an invoice?", "Explain subscriptions", "View tax reports"],
    },
    {
        # Payments & Gateways
        "patterns": [
            r"how (can i |to )collect payments?",
            r"how (do )?payments? work",
            r"explain payments?",
            r"razorpay",
            r"payment gateway",
            r"record payment",
            r"refund",
        ],
        "answer": (
            "Rooman Billing supports comprehensive payment operations:\n\n"
            "• **Online Checkout (Razorpay)**: Customers can pay invoices online via UPI, Credit/Debit Cards, NetBanking, and Wallets on hosted payment pages.\n"
            "• **Manual Recording**: Record bank transfers, NEFT/RTGS, cheques, or cash directly against any issued invoice.\n"
            "• **Partial Payments**: Accept installments; the system automatically updates the remaining balance due.\n"
            "• **Automated Receipts**: A downloadable PDF receipt is generated instantly upon payment confirmation.\n"
            "• **Refunds**: Process full or partial refunds directly with automatic credit note generation.\n\n"
            "Manage transactions and record offline payments under **Revenue → Payments**."
        ),
        "route": {"label": "Payments", "route": "/payments"},
        "chips": ["How to create an invoice?", "Where is dunning?", "Explain collections"],
    },
    {
        # Quotes & CPQ
        "patterns": [
            r"what is cpq",
            r"how (do )?quotes? work",
            r"explain quotes?",
            r"configure price quote",
            r"discount approvals?",
        ],
        "answer": (
            "**Quotes & CPQ (Configure, Price, Quote)** streamline B2B sales negotiations:\n\n"
            "• **Quote Proposals**: Create branded pricing quotes with expiry dates, custom terms, and tiered discounts.\n"
            "• **CPQ Bundling**: Package products, software licenses, and onboarding services into bundled deals.\n"
            "• **Approval Thresholds**: Automatically require management sign-off whenever sales discounts exceed configured limits (e.g., >20%).\n"
            "• **Instant Conversion**: Once a customer accepts a quote, convert it into an active subscription and issued invoice with one click.\n\n"
            "Explore quotes under **Revenue → Quotes** and pricing rules in **Revenue → CPQ**."
        ),
        "route": {"label": "CPQ Studio", "route": "/cpq"},
        "chips": ["Where are quotes?", "How to create an invoice?", "Explain proration"],
    },
    {
        # Trials
        "patterns": [
            r"how (do )?trials? work",
            r"what is a trial",
            r"trial management",
            r"free trial",
            r"trial conversion",
        ],
        "answer": (
            "**Trial Management** helps you onboard prospective customers smoothly:\n\n"
            "• Set custom trial durations (e.g., 7, 14, or 30 days) on subscription plans.\n"
            "• Choose between **Credit Card Required upfront** or **No Card Required**.\n"
            "• Automated email notifications remind users 3 days and 1 day before trial expiration.\n"
            "• Upon expiration, the trial converts into an active paid subscription or gracefully pauses access.\n\n"
            "Track trial performance and conversion rates under **Subscriptions → Trials**."
        ),
        "route": {"label": "Trial Management", "route": "/trials"},
        "chips": ["How do subscriptions work?", "Create an invoice", "Explain CPQ"],
    },
    {
        # Reports & Analytics
        "patterns": [
            r"where can i find reports",
            r"what reports are available",
            r"explain reports",
            r"financial reports",
            r"aging report",
            r"revenue intelligence",
        ],
        "answer": (
            "Rooman Billing provides deep financial and operational analytics:\n\n"
            "• **Receivables Aging**: Invoices categorized by 0–30, 31–60, 61–90, and 90+ days overdue to prioritize collections.\n"
            "• **Revenue Intelligence**: Live tracking of **MRR** (Monthly Recurring Revenue), **ARR**, Net Revenue Retention, and Churn.\n"
            "• **Tax Liability Reports**: Monthly breakdown of CGST, SGST, and IGST collected, exportable for GST filing.\n"
            "• **Payment Reconciliation**: Settlement reconciliation across gateways and payment modes.\n\n"
            "View and export reports in **Insights → Reports**."
        ),
        "route": {"label": "Reports", "route": "/reports"},
        "chips": ["What is our outstanding balance?", "What is our MRR?", "Show overdue invoices"],
    },
    {
        # Customers
        "patterns": [
            r"how (do )?customers? work",
            r"add (a )?customer",
            r"customer management",
            r"customer ledger",
        ],
        "answer": (
            "**Customer Management** centralizes all client records, contracts, and financial history:\n\n"
            "• **Profiles**: Store company legal name, billing/shipping addresses, GSTIN, and currency.\n"
            "• **Contacts**: Manage primary billing contacts and notification recipients.\n"
            "• **Customer Ledger**: View full transaction history, outstanding receivables, credit notes, and lifetime value.\n"
            "• **Customer Portal**: Provide clients with a branded self-service portal to view invoices and pay balances.\n\n"
            "Manage your accounts under **Workspace → Customers**."
        ),
        "route": {"label": "Customers", "route": "/customers"},
        "chips": ["How to create an invoice?", "Explain subscriptions", "Where are collections?"],
    },
    {
        # Projects & Timesheets
        "patterns": [
            r"how (do )?timesheets? work",
            r"how (do )?projects? work",
            r"time tracking",
            r"billable hours",
        ],
        "answer": (
            "Rooman Billing features integrated **Time & Project Billing** for agencies and service firms:\n\n"
            "• **Projects**: Set up client projects with fixed budgets or time-and-materials billing models.\n"
            "• **Timesheets**: Log daily and weekly team hours with billable vs. non-billable categorization.\n"
            "• **1-Click Invoice Generation**: Pull approved timesheet entries directly into an invoice line item with hourly rates.\n\n"
            "Track hours in **Operations → Timesheets** and manage engagements in **Operations → Projects**."
        ),
        "route": {"label": "Timesheets", "route": "/timesheets"},
        "chips": ["How to create an invoice?", "Where are expenses?", "View reports"],
    },
]


# ---------------------------------------------------------------------------
# Core Chatbot Logic
# ---------------------------------------------------------------------------
def process_chat(
    db: Session,
    ctx: CurrentContext,
    request: RoomiChatRequest,
) -> RoomiChatResponse:
    """Answers user queries with direct explanations, role awareness, and secondary navigation buttons."""
    user_prompt = request.message.strip()
    lowered = user_prompt.lower()
    conv_id = request.conversation_id or str(uuid.uuid4())

    # 1. Live Data Queries (grounded via ai_service)
    # Check if user is asking for specific live metrics
    is_live_data_query = (
        ("outstanding balance" in lowered or "total receivable" in lowered) or
        ("overdue count" in lowered or "how many overdue" in lowered) or
        ("what is our mrr" in lowered or "current mrr" in lowered)
    )
    if is_live_data_query:
        try:
            tool_name, answer, data, sources = ai_service._classify_and_answer(db, ctx.organization_id, user_prompt)
            if tool_name != "unsupported":
                sources_out = [
                    AISourceReferenceOut(
                        source_type=s.get("source_type", "metric"),
                        source_id=s.get("source_id"),
                        label=s.get("label", "Live Data"),
                        snippet=s.get("snippet"),
                    )
                    for s in sources
                ]
                hint = _match_route(user_prompt)
                return RoomiChatResponse(
                    reply=f"📊 **Live Billing Data** (Organization: *{ctx.organization.name}*):\n\n{answer}",
                    conversation_id=conv_id,
                    suggested_chips=["Show me reports", "Where is the action center?", "How to create an invoice?"],
                    sources=sources_out,
                    navigation=hint,
                    data=data,
                )
        except Exception:
            pass

    # 2. Greetings / Identity
    if any(re.search(rf"\b{g}\b", lowered) for g in ["hi", "hello", "hey", "who are you", "what can you do", "help me"]):
        first_name = ctx.user.full_name.split()[0] if ctx.user.full_name else "there"
        role_label = ctx.role.value.capitalize() if hasattr(ctx.role, "value") else str(ctx.role).capitalize()
        return RoomiChatResponse(
            reply=(
                f"Hi {first_name}! I'm **Roomi**, your AI billing assistant for **{ctx.organization.name}** 👋\n\n"
                f"You are logged in as **{role_label}**. I can answer any question about:\n"
                f"• **Invoices & Quotes**: How to create, customize, and issue GST-compliant bills\n"
                f"• **Subscriptions & Plans**: Renewal frequencies, trials, and proration calculations\n"
                f"• **Metered Billing**: Measuring consumption and finalizing usage events\n"
                f"• **Payments & Dunning**: Razorpay online collection and automated retry policies\n"
                f"• **Reports & Intelligence**: Aging analysis and revenue metrics\n"
                f"• **Navigating Rooman Billing**: Direct guidance to any screen\n\n"
                f"What would you like to know?"
            ),
            conversation_id=conv_id,
            suggested_chips=[
                "How does Rooman Billing work?",
                "How do I create an invoice?",
                "Explain subscriptions",
                "How does proration work?",
                "Where can I find reports?",
            ],
            navigation=RoomiNavigationHint(label="Dashboard", route="/dashboard"),
        )

    # 3. Direct Knowledge Topic Match (Prioritize thorough answers!)
    for topic in KNOWLEDGE_TOPICS:
        for pat in topic["patterns"]:
            if re.search(pat, lowered):
                nav_hint = RoomiNavigationHint(
                    label=topic["route"]["label"],
                    route=topic["route"]["route"],
                ) if "route" in topic else None
                return RoomiChatResponse(
                    reply=topic["answer"],
                    conversation_id=conv_id,
                    suggested_chips=topic.get("chips", ["How do I create an invoice?", "Explain proration", "View reports"]),
                    navigation=nav_hint,
                )

    # 4. Explicit Navigation Requests (Only when user explicitly asks where something is)
    is_nav_request = any(p in lowered for p in [
        "where is", "where can i find", "where are", "navigate to",
        "go to", "take me to", "open", "show me the page", "link to"
    ])
    if is_nav_request:
        matched_nav = _match_route(user_prompt)
        if matched_nav:
            return RoomiChatResponse(
                reply=(
                    f"You can find **{matched_nav.label}** in the sidebar navigation, or use the direct button below to jump straight to that screen:"
                ),
                conversation_id=conv_id,
                suggested_chips=["How does Rooman Billing work?", "How do I create an invoice?", "View reports"],
                navigation=matched_nav,
            )

    # 5. Optional External LLM Provider
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        try:
            llm_reply = _call_gemini(gemini_key, user_prompt, ctx)
            if llm_reply:
                return RoomiChatResponse(
                    reply=llm_reply,
                    conversation_id=conv_id,
                    suggested_chips=["How to create an invoice?", "Explain proration", "Where are reports?"],
                    navigation=_match_route(user_prompt),
                )
        except Exception:
            pass

    # 6. Default Fallback
    return RoomiChatResponse(
        reply=(
            f"Here is how that works in **Rooman Billing**:\n\n"
            f"Rooman Billing provides automated workflows for:\n"
            f"• **Invoices & Quotes**: Generating GST-compliant bills and customer proposals\n"
            f"• **Subscriptions**: Managing recurring plans, trial periods, and proration\n"
            f"• **Usage Metering**: Ingesting and rating dynamic consumption metrics\n"
            f"• **Payments**: Collecting via Razorpay or recording manual payments\n"
            f"• **Reports**: Analyzing aging, revenue intelligence, and tax summaries\n\n"
            f"Could you please clarify which specific feature you'd like guidance on?"
        ),
        conversation_id=conv_id,
        suggested_chips=[
            "How does Rooman Billing work?",
            "How do I create an invoice?",
            "Explain subscriptions",
            "How does proration work?",
            "Where can I find reports?",
        ],
        navigation=_match_route(user_prompt),
    )


def _call_gemini(api_key: str, prompt: str, ctx: CurrentContext) -> Optional[str]:
    """Optional external LLM bridge using Google Gemini when API key is provided."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    system_instruction = (
        f"You are Roomi, the expert AI assistant for the Rooman Billing SaaS platform. "
        f"You are speaking to {ctx.user.full_name or 'a team member'} (Role: {ctx.role.value}) "
        f"at organization '{ctx.organization.name}'. "
        f"Answer clearly, warmly, and concisely. Use bullet points for steps. "
        f"Direct users to the correct sections of Rooman Billing."
    )
    payload = {
        "contents": [{"role": "user", "parts": [{"text": f"{system_instruction}\n\nUser Question: {prompt}"}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 600},
    }
    resp = requests.post(url, json=payload, timeout=8)
    if resp.status_code == 200:
        data = resp.json()
        candidates = data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            if parts:
                return parts[0].get("text")
    return None
