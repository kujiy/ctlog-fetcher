import unittest
from src.share.cert_parser import JPCertificateParser

class TestExtractOrgType(unittest.TestCase):

    def setUp(self):
        self.parser = JPCertificateParser()

    def test_extract_org_type_prefecture(self):
        data = {'organization_type': 'unknown'}
        jp_domains = ['example.hokkaido.jp', 'example.tokyo.jp']  # Prefecture-type JP domains require a 3rd-level subdomain
        self.parser._extract_org_type(data, jp_domains)
        self.assertEqual(data['organization_type'], 'prefecture.jp')

    def test_extract_org_type_government(self):
        data = {'organization_type': 'unknown'}
        jp_domains = ['example.go.jp']
        self.parser._extract_org_type(data, jp_domains)
        self.assertEqual(data['organization_type'], 'go.jp')

    def test_extract_org_type_local_government(self):
        data = {'organization_type': 'unknown'}
        jp_domains = ['example.lg.jp']
        self.parser._extract_org_type(data, jp_domains)
        self.assertEqual(data['organization_type'], 'lg.jp')

    def test_extract_org_type_academic(self):
        data = {'organization_type': 'unknown'}
        jp_domains = ['example.ac.jp']
        self.parser._extract_org_type(data, jp_domains)
        self.assertEqual(data['organization_type'], 'ac.jp')

    def test_extract_org_type_commercial(self):
        data = {'organization_type': 'unknown'}
        jp_domains = ['example.co.jp']
        self.parser._extract_org_type(data, jp_domains)
        self.assertEqual(data['organization_type'], 'co.jp')

    def test_extract_org_type_network(self):
        data = {'organization_type': 'unknown'}
        jp_domains = ['example.ne.jp']
        self.parser._extract_org_type(data, jp_domains)
        self.assertEqual(data['organization_type'], 'ne.jp')

    def test_extract_org_type_organization(self):
        data = {'organization_type': 'unknown'}
        jp_domains = ['example.or.jp']
        self.parser._extract_org_type(data, jp_domains)
        self.assertEqual(data['organization_type'], 'or.jp')

    def test_extract_org_type_education(self):
        data = {'organization_type': 'unknown'}
        jp_domains = ['example.ed.jp']
        self.parser._extract_org_type(data, jp_domains)
        self.assertEqual(data['organization_type'], 'ed.jp')

    def test_extract_org_type_jpnic(self):
        data = {'organization_type': 'unknown'}
        jp_domains = ['example.ad.jp']
        self.parser._extract_org_type(data, jp_domains)
        self.assertEqual(data['organization_type'], 'ad.jp')

    def test_extract_org_type_unknown(self):
        data = {'organization_type': 'unknown'}
        jp_domains = ['example.unknown.jp']
        self.parser._extract_org_type(data, jp_domains)
        self.assertEqual(data['organization_type'], 'unknown')

    def test_extract_org_type_all_prefectures(self):
        prefectures = [
            'hokkaido.jp', 'aomori.jp', 'iwate.jp', 'miyagi.jp', 'akita.jp', 'yamagata.jp', 'fukushima.jp',
            'ibaraki.jp', 'tochigi.jp', 'gunma.jp', 'saitama.jp', 'chiba.jp', 'tokyo.jp', 'kanagawa.jp',
            'niigata.jp', 'toyama.jp', 'ishikawa.jp', 'fukui.jp', 'yamanashi.jp', 'nagano.jp', 'gifu.jp',
            'shizuoka.jp', 'aichi.jp', 'mie.jp', 'shiga.jp', 'kyoto.jp', 'osaka.jp', 'hyogo.jp', 'nara.jp',
            'wakayama.jp', 'tottori.jp', 'shimane.jp', 'okayama.jp', 'hiroshima.jp', 'yamaguchi.jp',
            'tokushima.jp', 'kagawa.jp', 'ehime.jp', 'kochi.jp', 'fukuoka.jp', 'saga.jp', 'nagasaki.jp',
            'kumamoto.jp', 'oita.jp', 'miyazaki.jp', 'kagoshima.jp', 'okinawa.jp'
        ]

        for prefecture in prefectures:
            with self.subTest(prefecture=prefecture):
                data = {'organization_type': 'unknown'}
                # Prefecture-type JP domains require a 3rd-level subdomain
                jp_domains = [f'example.{prefecture}']
                self.parser._extract_org_type(data, jp_domains)
                self.assertEqual(data['organization_type'], 'prefecture.jp')

if __name__ == '__main__':
    unittest.main()
