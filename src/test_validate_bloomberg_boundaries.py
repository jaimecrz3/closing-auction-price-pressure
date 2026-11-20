"""In-memory layout regression checks; no provider files or observations written."""
import unittest
from validate_bloomberg_workbook import instrument_columns, column_rows, last_row, validate_price_layout


def c(value=None, formula=None):
    return {'value':value, 'formula':formula, 'has_formula':formula is not None}


class Boundaries(unittest.TestCase):
    def test_new_instrument_and_action_rows_discovered(self):
        sheet={'cells':{'A1':c('SPY US EQUITY'),'DY1':c('NEW US EQUITY'),
                        'A100':c('44000'),'DY100':c('44000')}}
        self.assertEqual(len(instrument_columns(sheet,7)),2)
        self.assertEqual(last_row(sheet),100)

    def test_membership_longer_than_503_and_formatting_ignored(self):
        sheet={'cells':{'A1':c('ONE UN'),'A504':c('TWO UN'),'A9999':c()}}
        self.assertEqual(column_rows(sheet,{1,2}),[1,504])
        self.assertEqual(last_row(sheet),504)

    def test_unmapped_volume_column_rejected(self):
        with self.assertRaisesRegex(ValueError,'Unmapped'):
            instrument_columns({'cells':{'A1':c('SPY UP EQUITY'),'C2':c(123)}},2)

    def test_price_extension_rejected(self):
        with self.assertRaisesRegex(ValueError,'expanded/moved'):
            validate_price_layout({'cells':{'A22':c(45000)}},{'cells':{}})


if __name__=='__main__':unittest.main()
