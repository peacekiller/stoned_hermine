class Diff:
    field: str
    old_val: object
    new_val: object

    def __init__(self, field: str, old_val: str, new_val: str) -> None:
        self.field = field
        self.old_val = old_val
        self.new_val = new_val

    def __repr__(self):
        return "{}: {} -> {}".format(self.field, self.old_val, self.new_val)


    def __str__(self):
        return "{}: {} -> {}".format(self.field, self.old_val, self.new_val)