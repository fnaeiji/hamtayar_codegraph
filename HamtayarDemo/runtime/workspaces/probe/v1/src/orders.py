"""Probe fixture module."""


def calculate_total(items):
    total = 0
    for item in items:
        total += item
    return total


class OrderProcessor:
    def __init__(self, name):
        self.name = name

    def process(self, items):
        return calculate_total(items)


def main():
    proc = OrderProcessor("demo")
    return proc.process([1, 2, 3])
