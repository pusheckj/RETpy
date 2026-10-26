"""FAQ sidebar component.

Renders a collapsible FAQ at the bottom of the sidebar explaining the
assumptions and controls used throughout the app.
"""
from __future__ import annotations


QUESTIONS: list[tuple[str, str]] = [
    (
        "What is a Monte Carlo simulation?",
        "Instead of assuming one average return, the app runs thousands of "
        "randomized year-by-year market sequences based on historical stock and "
        "bond behavior. Each one plays out a different possible future, and the "
        "app counts how many succeed. \"80% success at age 55\" means 8 out of "
        "10 simulated futures last through your plan-until age (95 by default).",
    ),
    (
        "What's a good \"target success rate\"?",
        "80% is a common default. It balances not running out of money against "
        "working extra years for little gain. Many early retirees aim for "
        "90-95%. Past about 90%, each extra year of work adds very little.",
    ),
    (
        "What do Conservative, Historical and Pessimistic mean?",
        "They are three sets of assumed returns, after inflation. "
        "**Historical** is the 1926-2024 US average (about 8.7% stocks, 3.1% "
        "bonds). **Conservative** is lower (about 7% and 2%). **Pessimistic** "
        "is a stress test (about 5% and 1%). Many planners use Conservative. "
        "Treat a Historical result as the optimistic end of the range.",
    ),
    (
        "What is the \"glide path\"?",
        "It's your mix of stocks and bonds over time. Mostly stocks grows "
        "faster but swings more. More bonds is steadier but grows slower. A "
        "glide path starts out stock-heavy and shifts toward bonds as you "
        "near retirement, reaching a more conservative mix by 75 or so. "
        "Target-date funds from Fidelity and Vanguard do this for you.",
    ),
    (
        "What are Roth conversions, and should I turn them on?",
        "A Roth conversion moves money from a traditional 401(k) or IRA into a "
        "Roth. You pay income tax on it now, but later withdrawals are "
        "tax-free and have no required minimum distributions (RMDs). It works "
        "best in early retirement, when your income is low and Social Security "
        "hasn't started. Turn it on if you'll have large traditional balances "
        "at retirement.",
    ),
    (
        "What are \"spending guardrails\"?",
        "Rather than spend the same amount every year, the plan trims "
        "flexible spending when your portfolio falls below 70% of its target. "
        "It doesn't spend more when the portfolio is ahead. About 30% of "
        "non-housing spending counts as flexible, and the trim is 15% of that "
        "(about 4.5% of spending). Housing is never cut. Guardrails raise your "
        "chance of success, at the cost of tighter spending in bad markets.",
    ),
    (
        "What's a safe withdrawal rate?",
        "The classic \"4% rule\" says you can withdraw 4% of your starting "
        "portfolio each year, adjusted for inflation, and it should last 30 "
        "years. If you retire earlier and need it to last 40 years or more, "
        "3.25-3.5% is a safer starting point. The Withdrawal tab shows this "
        "for your plan.",
    ),
    (
        "Why does my Social Security estimate matter?",
        "Social Security adjusts for inflation and covers roughly 30-50% of "
        "retirement spending for a typical earner. An estimate that's off can "
        "move your earliest retirement age by 5 years or more. Get your own "
        "number at [ssa.gov/myaccount](https://www.ssa.gov/myaccount).",
    ),
    (
        "What about healthcare costs?",
        "The years before Medicare (ages 50-64) are often the most expensive. "
        "ACA premiums can run \\$20k or more a year for a couple without "
        "subsidies. Medicare starts at 65 and costs about \\$8-15k a year for "
        "a couple, including supplemental coverage. The app models both phases.",
    ),
    (
        "What if I rent, or I'm single?",
        "If you rent, choose Renting under Expenses and enter your rent. If "
        "you're single, choose \"Just me\" under About you. The partner inputs "
        "disappear, and the plan has no partner accounts, pay, savings or "
        "Social Security. If you and your partner aren't married, choose "
        "\"Me and my partner (not married)\".",
    ),
    (
        "How do I save my inputs?",
        "Open Settings (top right) and choose Save / Load profile. Download "
        "your inputs as a JSON file, then upload it later to restore them. The "
        "file stays on your computer.",
    ),
    (
        "What isn't modeled?",
        "Pensions, rental real estate, qualified charitable distributions, "
        "inherited IRAs, tax-loss harvesting, SEP-IRAs, solo 401(k)s, city and "
        "county income taxes, and the child tax credit. All 50 states and DC "
        "have tax tables (some are approximate). If yours looks wrong, choose "
        "\"Another state (flat rate)\" under Taxes and enter a rate.",
    ),
]


def render(st) -> None:
    with st.expander("FAQ: what do these settings mean?", expanded=False, icon=":material/help:"):
        for question, answer in QUESTIONS:
            with st.expander(question, expanded=False):
                st.markdown(answer)
