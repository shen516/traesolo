import logging
import re
from typing import List, Dict, Optional
from datetime import datetime
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class LeagueCrawler:
    """联赛数据采集器 - 从 liansai.500.com 采集联赛信息"""
    
    base_url = 'https://liansai.500.com/'
    
    category_map = {
        '国际赛事': 'international',
        '欧洲赛事': 'europe',
        '美洲赛事': 'america',
        '亚洲赛事': 'asia',
        '非洲赛事': 'africa',
    }
    
    region_map = {
        'international': '国际',
        'europe': '欧洲',
        'america': '美洲',
        'asia': '亚洲',
        'africa': '非洲',
    }
    
    default_icons = {
        'international': '🌍',
        'europe': '🇪🇺',
        'america': '🌎',
        'asia': '🌏',
        'africa': '🌍',
    }
    
    country_flag_map = {
        '英格兰': '🏴󠁧󠁢󠁥󠁮󠁧󠁿',
        '英国': '🏴󠁧󠁢󠁥󠁮󠁧󠁿',
        '苏格兰': '🏴󠁧󠁢󠁳󠁣󠁴󠁿',
        '威尔士': '🏴󠁧󠁢󠁷󠁬󠁳󠁿',
        '北爱尔兰': '🇬🇧',
        '西班牙': '🇪🇸',
        '德国': '🇩🇪',
        '意大利': '🇮🇹',
        '法国': '🇫🇷',
        '葡萄牙': '🇵🇹',
        '荷兰': '🇳🇱',
        '比利时': '🇧🇪',
        '奥地利': '🇦🇹',
        '瑞士': '🇨🇭',
        '丹麦': '🇩🇰',
        '瑞典': '🇸🇪',
        '挪威': '🇳🇴',
        '芬兰': '🇫🇮',
        '俄罗斯': '🇷🇺',
        '波兰': '🇵🇱',
        '捷克': '🇨🇿',
        '匈牙利': '🇭🇺',
        '希腊': '🇬🇷',
        '土耳其': '🇹🇷',
        '乌克兰': '🇺🇦',
        '克罗地亚': '🇭🇷',
        '塞尔维亚': '🇷🇸',
        '斯洛伐克': '🇸🇰',
        '斯洛文尼亚': '🇸🇮',
        '罗马尼亚': '🇷🇴',
        '保加利亚': '🇧🇬',
        '爱尔兰': '🇮🇪',
        '冰岛': '🇮🇸',
        '卢森堡': '🇱🇺',
        '马耳他': '🇲🇹',
        '亚美尼亚': '🇦🇲',
        '阿塞拜疆': '🇦🇿',
        '白俄罗斯': '🇧🇾',
        '波黑': '🇧🇦',
        '塞浦路斯': '🇨🇾',
        '爱沙尼亚': '🇪🇪',
        '格鲁吉亚': '🇬🇪',
        '哈萨克斯坦': '🇰🇿',
        '拉脱维亚': '🇱🇻',
        '立陶宛': '🇱🇹',
        '马其顿': '🇲🇰',
        '摩尔多瓦': '🇲🇩',
        '黑山': '🇲🇪',
        '北马其顿': '🇲🇰',
        '阿尔巴尼亚': '🇦🇱',
        '安道尔': '🇦🇩',
        '直布罗陀': '🇬🇮',
        '圣马力诺': '🇸🇲',
        '列支敦士登': '🇱🇮',
        '摩纳哥': '🇲🇨',
        '日本': '🇯🇵',
        '韩国': '🇰🇷',
        '中国': '🇨🇳',
        '澳大利亚': '🇦🇺',
        '沙特': '🇸🇦',
        '伊朗': '🇮🇷',
        '阿联酋': '🇦🇪',
        '卡塔尔': '🇶🇦',
        '伊拉克': '🇮🇶',
        '科威特': '🇰🇼',
        '阿曼': '🇴🇲',
        '乌兹别克斯坦': '🇺🇿',
        '巴林': '🇧🇭',
        '约旦': '🇯🇴',
        '叙利亚': '🇸🇾',
        '黎巴嫩': '🇱🇧',
        '巴勒斯坦': '🇵🇸',
        '也门': '🇾🇪',
        '朝鲜': '🇰🇵',
        '越南': '🇻🇳',
        '泰国': '🇹🇭',
        '马来西亚': '🇲🇾',
        '新加坡': '🇸🇬',
        '印度尼西亚': '🇮🇩',
        '菲律宾': '🇵🇭',
        '缅甸': '🇲🇲',
        '柬埔寨': '🇰🇭',
        '老挝': '🇱🇦',
        '东帝汶': '🇹🇱',
        '印度': '🇮🇳',
        '巴基斯坦': '🇵🇰',
        '孟加拉国': '🇧🇩',
        '斯里兰卡': '🇱🇰',
        '尼泊尔': '🇳🇵',
        '阿富汗': '🇦🇫',
        '马尔代夫': '🇲🇻',
        '不丹': '🇧🇹',
        '哈萨克斯坦': '🇰🇿',
        '吉尔吉斯斯坦': '🇰🇬',
        '塔吉克斯坦': '🇹🇯',
        '土库曼斯坦': '🇹🇲',
        '蒙古': '🇲🇳',
        '中国香港': '🇭🇰',
        '中国澳门': '🇲🇴',
        '中国台北': '🇹🇼',
        '美国': '🇺🇸',
        '加拿大': '🇨🇦',
        '墨西哥': '🇲🇽',
        '巴西': '🇧🇷',
        '阿根廷': '🇦🇷',
        '哥伦比亚': '🇨🇴',
        '智利': '🇨🇱',
        '秘鲁': '🇵🇪',
        '乌拉圭': '🇺🇾',
        '巴拉圭': '🇵🇾',
        '委内瑞拉': '🇻🇪',
        '厄瓜多尔': '🇪🇨',
        '玻利维亚': '🇧🇴',
        '哥斯达黎加': '🇨🇷',
        '巴拿马': '🇵🇦',
        '洪都拉斯': '🇭🇳',
        '萨尔瓦多': '🇸🇻',
        '危地马拉': '🇬🇹',
        '古巴': '🇨🇺',
        '牙买加': '🇯🇲',
        '特立尼达': '🇹🇹',
        '海地': '🇭🇹',
        '多米尼加': '🇩🇴',
        '尼加拉瓜': '🇳🇮',
        '伯利兹': '🇧🇿',
        '巴巴多斯': '🇧🇧',
        '圭亚那': '🇬🇾',
        '苏里南': '🇸🇷',
        '法属圭亚那': '🇬🇫',
        '非洲': '🌍',
        '埃及': '🇪🇬',
        '南非': '🇿🇦',
        '尼日利亚': '🇳🇬',
        '喀麦隆': '🇨🇲',
        '摩洛哥': '🇲🇦',
        '突尼斯': '🇹🇳',
        '阿尔及利亚': '🇩🇿',
        '加纳': '🇬🇭',
        '科特迪瓦': '🇨🇮',
        '塞内加尔': '🇸🇳',
        '布基纳法索': '🇧🇫',
        '马里': '🇲🇱',
        '尼日尔': '🇳🇪',
        '贝宁': '🇧🇯',
        '多哥': '🇹🇬',
        '几内亚': '🇬🇳',
        '几内亚比绍': '🇬🇼',
        '塞拉利昂': '🇸🇱',
        '利比里亚': '🇱🇷',
        '科摩罗': '🇰🇲',
        '冈比亚': '🇬🇲',
        '毛里塔尼亚': '🇲🇷',
        '佛得角': '🇨🇻',
        '赤道几内亚': '🇬🇶',
        '加蓬': '🇬🇦',
        '刚果': '🇨🇬',
        '刚果金': '🇨🇩',
        '安哥拉': '🇦🇴',
        '赞比亚': '🇿🇲',
        '津巴布韦': '🇿🇼',
        '马拉维': '🇲🇼',
        '莫桑比克': '🇲🇿',
        '南非': '🇿🇦',
        '斯威士兰': '🇸🇿',
        '莱索托': '🇱🇸',
        '马达加斯加': '🇲🇬',
        '毛里求斯': '🇲🇺',
        '塞舌尔': '🇸🇨',
        '肯尼亚': '🇰🇪',
        '坦桑尼亚': '🇹🇿',
        '乌干达': '🇺🇬',
        '卢旺达': '🇷🇼',
        '布隆迪': '🇧🇮',
        '埃塞俄比亚': '🇪🇹',
        '厄立特里亚': '🇪🇷',
        '索马里': '🇸🇴',
        '吉布提': '🇩🇯',
        '南苏丹': '🇸🇸',
        '苏丹': '🇸🇩',
        '利比亚': '🇱🇾',
        '苏丹': '🇸🇩',
        '南苏丹': '🇸🇸',
        '乍得': '🇹🇩',
        '中非': '🇨🇫',
        '尼日尔': '🇳🇪',
    }
    
    league_country_map = {
        '英超': '英格兰', '英冠': '英格兰', '英甲': '英格兰', '英乙': '英格兰', '英足总杯': '英格兰', '英联赛杯': '英格兰',
        '西甲': '西班牙', '西乙': '西班牙', '国王杯': '西班牙', '西超杯': '西班牙',
        '德甲': '德国', '德乙': '德国', '德国杯': '德国', '德超杯': '德国',
        '意甲': '意大利', '意乙': '意大利', '意大利杯': '意大利', '意超杯': '意大利',
        '法甲': '法国', '法乙': '法国', '法国杯': '法国', '法超杯': '法国',
        '葡超': '葡萄牙', '葡甲': '葡萄牙', '葡杯': '葡萄牙', '葡超杯': '葡萄牙',
        '荷甲': '荷兰', '荷乙': '荷兰', '荷兰杯': '荷兰', '荷超杯': '荷兰',
        '比甲': '比利时', '比乙': '比利时', '比杯': '比利时',
        '奥甲': '奥地利', '奥乙': '奥地利',
        '瑞超': '瑞士', '瑞甲': '瑞士',
        '丹超': '丹麦', '丹甲': '丹麦',
        '瑞典超': '瑞典', '瑞典甲': '瑞典',
        '挪超': '挪威', '挪甲': '挪威',
        '芬超': '芬兰', '芬甲': '芬兰',
        '俄超': '俄罗斯', '俄甲': '俄罗斯', '俄罗斯杯': '俄罗斯',
        '波超': '波兰', '波甲': '波兰',
        '捷甲': '捷克', '捷乙': '捷克',
        '匈甲': '匈牙利', '匈乙': '匈牙利',
        '希超': '希腊', '希甲': '希腊',
        '土超': '土耳其', '土甲': '土耳其', '土耳其杯': '土耳其',
        '乌超': '乌克兰', '乌甲': '乌克兰',
        '克甲': '克罗地亚', '克乙': '克罗地亚',
        '塞甲': '塞尔维亚', '塞乙': '塞尔维亚',
        '斯甲': '斯洛伐克', '斯乙': '斯洛伐克',
        '斯亚甲': '斯洛文尼亚',
        '罗甲': '罗马尼亚', '罗乙': '罗马尼亚',
        '保甲': '保加利亚', '保乙': '保加利亚',
        '爱超': '爱尔兰',
        '冰超': '冰岛',
        '苏超': '苏格兰', '苏甲': '苏格兰', '苏乙': '苏格兰', '苏格兰杯': '苏格兰',
        '威超': '威尔士',
        '北爱超': '北爱尔兰',
        '欧国联': '欧洲', '欧冠': '欧洲', '欧联': '欧洲', '欧协联': '欧洲', '欧洲杯': '欧洲',
        '世界杯': '国际', '世冠杯': '国际', '世俱杯': '国际', '友谊赛': '国际', '奥运': '国际',
        '日职联': '日本', 'J1': '日本', 'J2': '日本', 'J3': '日本', '天皇杯': '日本', '日联杯': '日本',
        '韩K联': '韩国', 'K1': '韩国', 'K2': '韩国', 'K3': '韩国', 'K4': '韩国', '韩国杯': '韩国',
        '中超': '中国', '中甲': '中国', '中乙': '中国', '中国杯': '中国', '足协杯': '中国',
        '澳超': '澳大利亚', '澳甲': '澳大利亚', '澳维超': '澳大利亚', '澳杯': '澳大利亚',
        '沙特超': '沙特', '沙特甲': '沙特', '沙特杯': '沙特',
        '伊朗超': '伊朗', '伊朗甲': '伊朗',
        '阿联酋超': '阿联酋', '阿联酋甲': '阿联酋',
        '卡塔尔超': '卡塔尔',
        '伊拉克超': '伊拉克',
        '科威特超': '科威特',
        '乌兹别克超': '乌兹别克斯坦',
        '泰国超': '泰国', '泰甲': '泰国', '泰国杯': '泰国',
        '越南超': '越南', '越南甲': '越南',
        '马来西亚超': '马来西亚', '马来甲': '马来西亚',
        '新加坡超': '新加坡',
        '印度超': '印度', '印度甲': '印度',
        '美职联': '美国', '美冠': '美国', '美公开赛': '美国',
        '加职联': '加拿大',
        '墨超': '墨西哥', '墨甲': '墨西哥', '墨杯': '墨西哥',
        '巴甲': '巴西', '巴乙': '巴西', '巴西杯': '巴西', '巴超杯': '巴西',
        '阿甲': '阿根廷', '阿乙': '阿根廷', '阿根廷杯': '阿根廷',
        '哥伦甲': '哥伦比亚', '哥伦乙': '哥伦比亚',
        '智甲': '智利', '智乙': '智利',
        '秘鲁甲': '秘鲁', '秘鲁乙': '秘鲁',
        '乌拉圭甲': '乌拉圭', '乌拉圭乙': '乌拉圭',
        '巴拉圭甲': '巴拉圭',
        '委内超': '委内瑞拉',
        '厄甲': '厄瓜多尔',
        '玻甲': '玻利维亚',
        '美洲杯': '美洲', '美锦赛': '美洲',
        '埃及超': '埃及', '埃及甲': '埃及', '埃及杯': '埃及',
        '南非超': '南非', '南非甲': '南非',
        '尼日超': '尼日利亚',
        '喀麦隆甲': '喀麦隆', '喀麦隆乙': '喀麦隆',
        '摩洛哥超': '摩洛哥', '摩洛哥甲': '摩洛哥',
        '突尼斯超': '突尼斯',
        '阿尔及利亚超': '阿尔及利亚',
        '加纳超': '加纳',
        '科特迪瓦超': '科特迪瓦',
        '塞内加尔超': '塞内加尔',
        '津巴超': '津巴布韦',
        '埃塞俄比亚超': '埃塞俄比亚',
    }
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        })
    
    def crawl(self) -> List[Dict]:
        """采集所有联赛数据"""
        leagues = []
        try:
            r = self.session.get(self.base_url, timeout=30)
            try:
                text = r.content.decode('gbk', errors='replace')
            except:
                text = r.content.decode('utf-8', errors='replace')
            
            soup = BeautifulSoup(text, 'html.parser')
            main_wrap = soup.find('div', id='allraceMainWrap')
            
            if not main_wrap:
                logger.warning("No allraceMainWrap found")
                return leagues
            
            sections = main_wrap.find_all('div', recursive=False)
            
            for idx, section in enumerate(sections):
                category_name = self._get_category_name(idx)
                category_code = self.category_map.get(category_name, 'international')
                
                uls = section.find_all('ul')
                for ul in uls:
                    lis = ul.find_all('li')
                    for li in lis:
                        links = li.find_all('a', href=True)
                        for link in links:
                            href = link['href']
                            if '/zuqiu-' in href:
                                league_data = self._parse_league_link(link, category_code, category_name)
                                if league_data:
                                    leagues.append(league_data)
            
            logger.info(f"Crawled {len(leagues)} leagues from liansai.500.com")
            
        except Exception as e:
            logger.error(f"Failed to crawl liansai.500.com: {str(e)}")
        
        return leagues
    
    def _get_category_name(self, index: int) -> str:
        """根据section索引获取赛事类型名称"""
        categories = ['国际赛事', '欧洲赛事', '美洲赛事', '亚洲赛事', '非洲赛事']
        if index < len(categories):
            return categories[index]
        return '国际赛事'
    
    def _parse_league_link(self, link, category_code: str, category_name: str) -> Optional[Dict]:
        """解析联赛链接"""
        try:
            league_name = link.text.strip()
            if not league_name:
                return None
            
            href = link['href']
            match = re.search(r'/zuqiu-(\d+)/', href)
            if not match:
                return None
            
            league_id = f"LS{match.group(1)}"
            source_url = href if href.startswith('http') else f"https:{href}"
            
            level = self._determine_level(league_name, category_code)
            region = self.region_map.get(category_code, '国际')
            icon = self.default_icons.get(category_code, '⚽')
            
            country = None
            flag = None
            if category_code != 'international':
                country = self._determine_country(league_name)
                if country:
                    flag = self.country_flag_map.get(country)

            from services.league_parent import infer_parent_id
            parent_id = infer_parent_id(league_name, country, level, category_code, league_id)
            
            return {
                'id': league_id,
                'name': league_name,
                'icon': icon,
                'region': region,
                'category': category_code,
                'country': country,
                'flag': flag,
                'level': level,
                'parent_id': parent_id,
                'avg_goals': 2.70,
                'is_active': True,
                'source_url': source_url,
            }
        
        except Exception as e:
            logger.error(f"Failed to parse league link: {str(e)}")
            return None
    
    def _determine_country(self, league_name: str) -> Optional[str]:
        """根据联赛名称确定国家"""
        for key, country in self.league_country_map.items():
            if key in league_name:
                return country
        
        for country in self.country_flag_map.keys():
            if country in league_name:
                return country
        
        return None
    
    def _determine_level(self, league_name: str, category_code: str) -> int:
        """根据联赛名称确定级别"""
        if '杯' in league_name:
            if any(keyword in league_name for keyword in ['世界杯', '欧洲杯', '美洲杯', '亚洲杯', '非洲杯', '欧冠', '欧联', '世冠']):
                return 1
            elif any(keyword in league_name for keyword in ['联赛杯', '超级杯', '足总杯', '国王杯', '德国杯', '意大利杯']):
                return 2
            else:
                return 3
        
        if category_code == 'international':
            return 1
        
        if any(keyword in league_name for keyword in ['甲级', '顶级', '一级', '中超', '英超', '西甲', '德甲', '意甲', '法甲']):
            return 1
        
        if any(keyword in league_name for keyword in ['乙级', '二级', 'J2', 'K2']):
            return 2
        
        if any(keyword in league_name for keyword in ['丙级', '三级', 'J3', 'K3', 'K4']):
            return 3
        
        return 2
    
    def crawl_league_detail(self, league_url: str) -> Optional[Dict]:
        """采集联赛详情页面"""
        try:
            r = self.session.get(league_url, timeout=30)
            try:
                text = r.content.decode('gbk', errors='replace')
            except:
                text = r.content.decode('utf-8', errors='replace')
            
            soup = BeautifulSoup(text, 'html.parser')
            
            detail = {}
            
            title = soup.find('title')
            if title:
                detail['title'] = title.text.strip()
            
            breadcrumb = soup.find('div', class_='bread-crumb')
            if breadcrumb:
                detail['breadcrumb'] = breadcrumb.text.strip()
            
            return detail
            
        except Exception as e:
            logger.error(f"Failed to crawl league detail {league_url}: {str(e)}")
            return None
