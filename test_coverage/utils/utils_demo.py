class UtilsDemo:
    def __init__(self, a, b):
        self.a = a
        self.b = b

    def multiply(self):
        return self.a * self.b

    def divide(self):
        if self.b == 0:
            raise ValueError('除数不能为0')
        return self.a / self.b 