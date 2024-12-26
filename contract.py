counter = Variable()
messages = Hash()

@construct
def init():
    counter.set(0)

@export
def save_msg(msg: str, recipient: str):
    counter.set(counter.get() + 1)

    messages[counter.get()] = {
        'sender': ctx.signer,
        'message': msg,
        'receiver': recipient,
        'timestamp': now
    }
