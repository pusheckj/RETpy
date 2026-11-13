"""The age ranges every age widget uses, in one place so they stay coherent.

The rule they keep: whatever age you can enter as your own, you can also pick as
your target retirement age ("already retired"), and the plan-until slider can
still reach past it. So no combination of age inputs is a dead end.

    your age / partner's age   AGE_MIN .. AGE_MAX            (99: plan-until stops at 100)
    target retirement ages     TARGET_MIN .. TARGET_MAX      (the same top as AGE_MAX)
    plan-until ages            PLAN_UNTIL_MIN .. PLAN_UNTIL_MAX
"""
AGE_MIN = 18
AGE_MAX = 99
TARGET_MIN = 25
TARGET_MAX = AGE_MAX
PLAN_UNTIL_MIN = 75
PLAN_UNTIL_MAX = 100
