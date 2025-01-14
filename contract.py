balances = Hash(default_value=0)
metadata = Hash()

def transfer_from(amount: float, to: str, main_account: str):
    assert amount > 0, 'Cannot send negative balances!'
    assert balances[main_account, ctx.caller] >= amount, \
    f'Not enough coins approved to send! You have {balances[main_account, ctx.caller]} and are trying to spend {amount}'

    dir

    assert balances[main_account] >= amount, 'Not enough coins to send!'
    balances[main_account, ctx.caller] -= amount
    balances[main_account] -= amount
    balances[to] += amount
