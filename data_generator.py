"""
Synthetic data generator for Recon Sentry.

Generates four source datasets that simulate the platform's operational data:

  merchant_sales           - what merchants sold, from their commerce system
  contracts                - what the platform recorded as protection contracts sold
  claims                   - customer claims filed via servicers
  servicer_reimbursements  - what the platform paid out to servicers

The generator deliberately plants known break patterns so the dbt
reconciliation models have something to catch. Every planted break
is logged to `data/planted_breaks.json` so the demo can assert that
the pipeline found them.

Break patterns planted (all realistic):
  timing_break        - contract exists but merchant sale not yet remitted
  amount_break        - merchant remittance amount differs from contract premium
  orphan_contract     - contract in the platform, no matching merchant sale
  orphan_claim        - claim filed against non-existent contract
  duplicate_claim     - same underlying claim submitted twice
  overpayment         - reimbursement exceeds claim amount
  coverage_exceeded   - cumulative payouts exceed contract coverage limit

Run: python data_generator.py
Output CSVs go to seeds/ so dbt seed can pick them up.
"""
from __future__ import annotations

import csv
import json
import random
import uuid
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).parent
SEEDS_DIR = ROOT / "seeds"
SEEDS_DIR.mkdir(exist_ok=True)


# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------

random.seed(42)  # reproducible

NUM_MERCHANTS = 8
NUM_SERVICERS = 4
NUM_SALES = 300
CLAIM_RATE = 0.15          # 15 percent of contracts eventually get claims
START_DATE = datetime(2025, 1, 1)
END_DATE = datetime(2025, 6, 30)


MERCHANTS = [
    {"merchant_id": f"M{i:03d}", "merchant_name": name, "category": cat}
    for i, (name, cat) in enumerate([
        ("Sleep Country", "furniture"),
        ("Sur La Table", "kitchen"),
        ("RealTruck", "auto"),
        ("Sonos", "electronics"),
        ("Glamnetic", "beauty"),
        ("Nectar", "furniture"),
        ("iRobot", "electronics"),
        ("Visionworks", "eyewear"),
    ], start=1)
]

SERVICERS = [
    {"servicer_id": f"S{i:03d}", "servicer_name": name}
    for i, name in enumerate([
        "AllRepair Network",
        "FastFix Partners",
        "HomeService Guild",
        "ProTech Servicers",
    ], start=1)
]


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def rand_date(start: datetime, end: datetime) -> datetime:
    delta = end - start
    return start + timedelta(days=random.randint(0, delta.days))


def money(low: float, high: float) -> float:
    return round(random.uniform(low, high), 2)


# ------------------------------------------------------------------
# Data generation
# ------------------------------------------------------------------

def generate() -> dict:
    sales = []
    contracts = []
    claims = []
    reimbursements = []
    planted = []  # log of intentional breaks

    for _ in range(NUM_SALES):
        merchant = random.choice(MERCHANTS)
        sale_date = rand_date(START_DATE, END_DATE - timedelta(days=30))
        sale_id = str(uuid.uuid4())[:12]
        contract_id = str(uuid.uuid4())[:12]
        product_price = money(50, 2000)
        premium = round(product_price * random.uniform(0.05, 0.15), 2)

        merchant_row = {
            "sale_id": sale_id,
            "merchant_id": merchant["merchant_id"],
            "sale_date": sale_date.strftime("%Y-%m-%d"),
            "product_price": product_price,
            "premium_charged": premium,
            "remittance_amount": premium,     # default matches; break generator may override
            "remittance_date": (sale_date + timedelta(days=random.randint(1, 15))).strftime("%Y-%m-%d"),
            "customer_email": f"cust_{sale_id[:6]}@example.com",
        }

        contract_row = {
            "contract_id": contract_id,
            "sale_id": sale_id,
            "merchant_id": merchant["merchant_id"],
            "issued_date": sale_date.strftime("%Y-%m-%d"),
            "premium": premium,
            "coverage_limit": product_price,
            "term_months": random.choice([12, 24, 36]),
            "status": "active",
        }

        sales.append(merchant_row)
        contracts.append(contract_row)

    # ---------- plant breaks ------------------------------------------------

    # 1. amount_break: change 8 remittances to a different amount
    for row in random.sample(sales, 8):
        original = row["remittance_amount"]
        row["remittance_amount"] = round(original * random.uniform(0.7, 0.95), 2)
        planted.append({
            "break_type": "amount_break",
            "sale_id": row["sale_id"],
            "detail": f"remittance {row['remittance_amount']} vs premium {original}",
        })

    # 2. timing_break: null out remittance_date on 6 sales (still unpaid)
    for row in random.sample([s for s in sales if s["sale_id"] not in {p['sale_id'] for p in planted}], 6):
        row["remittance_amount"] = 0.0
        row["remittance_date"] = ""
        planted.append({
            "break_type": "timing_break",
            "sale_id": row["sale_id"],
            "detail": "remittance not yet received",
        })

    # 3. orphan_contract: add 5 contracts with no matching sale
    for _ in range(5):
        merchant = random.choice(MERCHANTS)
        contract_id = str(uuid.uuid4())[:12]
        contracts.append({
            "contract_id": contract_id,
            "sale_id": str(uuid.uuid4())[:12],  # sale_id that does not exist in sales
            "merchant_id": merchant["merchant_id"],
            "issued_date": rand_date(START_DATE, END_DATE).strftime("%Y-%m-%d"),
            "premium": money(20, 200),
            "coverage_limit": money(200, 2000),
            "term_months": 12,
            "status": "active",
        })
        planted.append({
            "break_type": "orphan_contract",
            "contract_id": contract_id,
            "detail": "contract has no corresponding merchant sale",
        })

    # ---------- generate claims and reimbursements --------------------------

    real_contracts = [c for c in contracts if not any(p.get('contract_id') == c['contract_id'] and p['break_type'] == 'orphan_contract' for p in planted)]

    n_claims = int(len(real_contracts) * CLAIM_RATE)
    claim_contracts = random.sample(real_contracts, n_claims)

    for contract in claim_contracts:
        claim_id = str(uuid.uuid4())[:12]
        servicer = random.choice(SERVICERS)
        issued = datetime.strptime(contract["issued_date"], "%Y-%m-%d")
        claim_date = issued + timedelta(days=random.randint(30, 180))
        if claim_date > END_DATE:
            continue
        claim_amount = round(contract["coverage_limit"] * random.uniform(0.1, 0.8), 2)

        claim_row = {
            "claim_id": claim_id,
            "contract_id": contract["contract_id"],
            "servicer_id": servicer["servicer_id"],
            "claim_date": claim_date.strftime("%Y-%m-%d"),
            "claim_amount": claim_amount,
            "status": "approved",
        }
        claims.append(claim_row)

        reimb_row = {
            "reimbursement_id": str(uuid.uuid4())[:12],
            "claim_id": claim_id,
            "servicer_id": servicer["servicer_id"],
            "paid_date": (claim_date + timedelta(days=random.randint(7, 30))).strftime("%Y-%m-%d"),
            "paid_amount": claim_amount,
        }
        reimbursements.append(reimb_row)

    # 4. orphan_claim: add 4 claims for non-existent contracts
    for _ in range(4):
        claim_id = str(uuid.uuid4())[:12]
        servicer = random.choice(SERVICERS)
        claims.append({
            "claim_id": claim_id,
            "contract_id": str(uuid.uuid4())[:12],  # non-existent
            "servicer_id": servicer["servicer_id"],
            "claim_date": rand_date(START_DATE, END_DATE).strftime("%Y-%m-%d"),
            "claim_amount": money(50, 500),
            "status": "approved",
        })
        planted.append({
            "break_type": "orphan_claim",
            "claim_id": claim_id,
            "detail": "claim references non-existent contract",
        })

    # 5. duplicate_claim: pick 3 existing claims and add a duplicate reimbursement
    for claim in random.sample([c for c in claims if c["contract_id"] in {rc["contract_id"] for rc in real_contracts}], 3):
        dup_reimb = {
            "reimbursement_id": str(uuid.uuid4())[:12],
            "claim_id": claim["claim_id"],
            "servicer_id": claim["servicer_id"],
            "paid_date": (datetime.strptime(claim["claim_date"], "%Y-%m-%d") + timedelta(days=random.randint(10, 40))).strftime("%Y-%m-%d"),
            "paid_amount": claim["claim_amount"],
        }
        reimbursements.append(dup_reimb)
        planted.append({
            "break_type": "duplicate_claim",
            "claim_id": claim["claim_id"],
            "detail": "claim reimbursed twice",
        })

    # 6. overpayment: modify 4 reimbursements to exceed their claim amount
    for r in random.sample(reimbursements, 4):
        r["paid_amount"] = round(r["paid_amount"] * random.uniform(1.1, 1.5), 2)
        planted.append({
            "break_type": "overpayment",
            "reimbursement_id": r["reimbursement_id"],
            "detail": f"paid {r['paid_amount']} exceeds claim amount",
        })

    # 7. coverage_exceeded: force cumulative payouts on 2 contracts to exceed limit
    for contract in random.sample(real_contracts, 2):
        extra_claim_id = str(uuid.uuid4())[:12]
        extra_reimb_id = str(uuid.uuid4())[:12]
        servicer = random.choice(SERVICERS)
        claim_date = datetime.strptime(contract["issued_date"], "%Y-%m-%d") + timedelta(days=random.randint(30, 100))
        claims.append({
            "claim_id": extra_claim_id,
            "contract_id": contract["contract_id"],
            "servicer_id": servicer["servicer_id"],
            "claim_date": claim_date.strftime("%Y-%m-%d"),
            "claim_amount": contract["coverage_limit"] * 0.95,
            "status": "approved",
        })
        reimbursements.append({
            "reimbursement_id": extra_reimb_id,
            "claim_id": extra_claim_id,
            "servicer_id": servicer["servicer_id"],
            "paid_date": (claim_date + timedelta(days=15)).strftime("%Y-%m-%d"),
            "paid_amount": contract["coverage_limit"] * 0.95,
        })
        planted.append({
            "break_type": "coverage_exceeded",
            "contract_id": contract["contract_id"],
            "detail": "cumulative payouts will exceed coverage_limit",
        })

    return {
        "merchants": MERCHANTS,
        "servicers": SERVICERS,
        "merchant_sales": sales,
        "contracts": contracts,
        "claims": claims,
        "servicer_reimbursements": reimbursements,
        "planted_breaks": planted,
    }


def write_csv(rows: list[dict], path: Path) -> None:
    if not rows:
        return
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    data = generate()

    write_csv(data["merchants"], SEEDS_DIR / "merchants.csv")
    write_csv(data["servicers"], SEEDS_DIR / "servicers.csv")
    write_csv(data["merchant_sales"], SEEDS_DIR / "merchant_sales.csv")
    write_csv(data["contracts"], SEEDS_DIR / "contracts.csv")
    write_csv(data["claims"], SEEDS_DIR / "claims.csv")
    write_csv(data["servicer_reimbursements"], SEEDS_DIR / "servicer_reimbursements.csv")

    with (ROOT / "planted_breaks.json").open("w") as f:
        json.dump(data["planted_breaks"], f, indent=2)

    print(f"Generated {len(data['merchant_sales'])} sales, "
          f"{len(data['contracts'])} contracts, "
          f"{len(data['claims'])} claims, "
          f"{len(data['servicer_reimbursements'])} reimbursements.")
    print(f"Planted {len(data['planted_breaks'])} intentional breaks across "
          f"{len(set(p['break_type'] for p in data['planted_breaks']))} categories.")


if __name__ == "__main__":
    main()
