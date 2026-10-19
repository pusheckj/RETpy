"""FAQ sidebar component.

Renders a collapsible FAQ at the bottom of the sidebar to help users
understand the assumptions and controls used throughout the app.
"""
from __future__ import annotations


QUESTIONS: list[tuple[str, str]] = [
    (
        "What is a Monte Carlo simulation?",
        "Instead of assuming a single average return, we run thousands of "
        "randomized year-by-year sequences drawn from historical stock and bond "
        "behavior. Each \"simulation\" plays out a different hypothetical future, "
        "then we count the fraction that succeed. A result like \"80% success at "
        "age 55\" means 8 out of 10 simulated futures have you covered through "
        "age 95.",
    ),
    (
        "What's a good \"target success rate\"?",
        "80% is a common planner default — it balances \"don't run out\" against "
        "\"don't work 10 extra years for nothing.\" FIRE enthusiasts often target "
        "90–95%. The marginal value of extra years of work falls off quickly once "
        "success exceeds about 90%.",
    ),
    (
        "What are stock/bond returns? (Conservative vs Historical vs Pessimistic)",
        "**Historical** = 1926–2024 US market average (about 8.7% stocks / 3.1% "
        "bonds, real). **Conservative** = a planner-friendly haircut (about 7% / "
        "2%). **Pessimistic** = a stress test (about 5% / 1%). Most planners use "
        "Conservative; if you use Historical, treat the result as an optimistic "
        "upper bound.",
    ),
    (
        "What is the \"glide path\"?",
        "Your mix of stocks vs. bonds. **Aggressive** (mostly stocks) grows "
        "faster but swings more. **Conservative** (more bonds) is stable but "
        "grows slower. A \"glide path\" gradually shifts from aggressive near "
        "retirement age to more conservative by age 75+. Fidelity and Vanguard "
        "target-date funds do this automatically.",
    ),
    (
        "What are Roth conversions and should I enable them?",
        "Converting traditional 401(k)/IRA dollars into a Roth during low-income "
        "early-retirement years (before Social Security kicks in). You pay income "
        "tax now in a low bracket so future withdrawals are tax-free and not "
        "subject to RMDs at age 73/75. Enable it if you'll have significant "
        "Traditional balances at retirement.",
    ),
    (
        "What are \"spending guardrails\"?",
        "Instead of spending the same amount every year, you dial spending down "
        "about 15% when the portfolio drops below 70% of target, and hold steady "
        "when it's up. This Guyton-Klinger-style rule dramatically improves "
        "success rates at the cost of some lifestyle flexibility in bad markets.",
    ),
    (
        "What's a safe withdrawal rate?",
        "The classic \"4% rule\" (Trinity study) — you can withdraw 4% of your "
        "initial portfolio, inflation-adjusted, for 30 years with high success. "
        "For earlier retirement (40+ year horizons), many planners recommend "
        "3.25–3.5%. The Withdrawal tab visualizes this for your plan.",
    ),
    (
        "Why does my Social Security estimate matter?",
        "Social Security is inflation-adjusted and covers roughly 30–50% of "
        "retirement expenses for median earners. Getting this number wrong can "
        "swing your earliest-retirement-age result by 5+ years. Check your "
        "personalized estimate at [ssa.gov/myaccount](https://www.ssa.gov/myaccount).",
    ),
    (
        "What about healthcare costs?",
        "Pre-Medicare (ages 50–64) is often the most expensive phase of "
        "retirement — ACA premiums can run \\$20k+/yr for a couple without "
        "subsidies. Medicare kicks in at 65 (~\\$8–15k/yr for a couple, including "
        "supplemental coverage). The tool models both phases.",
    ),
    (
        "What if I don't own a home / am not married?",
        "Set home value and mortgage to \\$0 (you'll rent forever, and rent is "
        "already included in expenses). Set partner age to 0 and partner salary "
        "to 0 if single. The simulator handles both cleanly.",
    ),
    (
        "How do I save my inputs?",
        "Use the 💾 Save/Load expander at the top of the sidebar. Download the "
        "current config as JSON, then upload later to restore. The file is "
        "gitignored so it's safe to keep locally.",
    ),
    (
        "What's NOT modeled?",
        "Pension income, rental real estate, qualified charitable distributions, "
        "inherited IRAs, tax-loss harvesting, SEP-IRAs, sole-proprietor 401(k)s, "
        "and state tax other than California by default. Adjust "
        "`YOUR_MARGINAL_TAX_RATE` or the CA bracket in `config.py` to approximate "
        "other states.",
    ),
]


def render(st) -> None:
    with st.expander("FAQ — what do these settings mean?", expanded=False, icon=":material/help:"):
        for question, answer in QUESTIONS:
            with st.expander(question, expanded=False):
                st.markdown(answer)
