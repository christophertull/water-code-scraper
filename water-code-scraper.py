import requests
from bs4 import BeautifulSoup
import re
import os
import time
from urllib.parse import urljoin, urlparse, parse_qs
import json
from typing import List, Dict, Tuple

# ===== CONFIGURATION SECTION =====
# Add code sections to scrape here
CODE_SECTIONS_TO_SCRAPE = [
    {
        'code': 'WAT',
        'code_name': 'Water Code',
        'division': '6',
        'division_name': 'CONSERVATION, DEVELOPMENT, AND UTILIZATION OF STATE WATER RESOURCES',
        'parts': None  # None means scrape all parts in the division
    },
    {
        'code': 'HSC',
        'code_name': 'Health and Safety Code',
        'division': '104',
        'division_name': None,  # Will be determined from the website
        'parts': ['12']  # Only scrape Part 12 (Drinking Water)
    }
]

# Base configuration
BASE_URL = "https://leginfo.legislature.ca.gov"
REQUEST_DELAY = 1  # seconds between requests
OUTPUT_BASE_DIR = "california_legal_codes"

# Headers for requests
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# ===== END CONFIGURATION =====

def get_division_structure(code: str, division: str, specific_parts: List[str] = None) -> List[Dict]:
    """Get the structure of a division including all its parts"""
    url = f"{BASE_URL}/faces/codes_displayexpandedbranch.xhtml?tocCode={code}&division={division}.&title=&part=&chapter=&article="
    
    print(f"Fetching division structure from: {url}")
    response = requests.get(url, headers=HEADERS)
    response.raise_for_status()
    
    soup = BeautifulSoup(response.content, 'html.parser')
    
    parts_info = []
    
    content_div = soup.find('div', {'id': 'expandedbranchcodesid'})
    if not content_div:
        print(f"Could not find the main content div for {code} Division {division}")
        return []
    
    # Find all anchor tags that might contain parts
    for anchor in content_div.find_all('a', href=True):
        href = anchor['href']
        
        # Look for divs within the anchor that have the part text
        part_div = anchor.find('div', style=lambda x: x and 'margin-left:20px' in x)
        if not part_div:
            continue
            
        link_text = part_div.get_text(strip=True)
        
        # Must contain "PART" in the text
        if 'PART' not in link_text.upper():
            continue
            
        # Skip reserved sections
        if '(Reserved)' in link_text:
            continue
            
        # Parse URL to get part info
        parsed = urlparse(href)
        params = parse_qs(parsed.query)
        part = params.get('part', [''])[0]
        
        if not part:
            continue
            
        # If specific parts are requested, filter
        if specific_parts and part.rstrip('.') not in specific_parts:
            continue
            
        # Get the range if it exists (e.g., "116270-117130")
        range_div = anchor.find('div', style=lambda x: x and 'float:right' in x)
        range_text = range_div.get_text(strip=True) if range_div else ""
        
        part_info = {
            'url': urljoin(BASE_URL, href),
            'title': link_text,
            'part': part,
            'code': code,
            'division': division,
            'has_chapters': 'displayexpandedbranch' in href,
            'range': range_text,
            'chapters': []
        }
        
        parts_info.append(part_info)
        print(f"  Found part: {link_text} ({range_text})")
    
    return parts_info

def get_chapters_for_part(part_url: str, code: str, division: str, part: str) -> List[Dict]:
    """Get all chapters for a part that has expandable chapters"""
    print(f"    Fetching chapters from: {part_url}")
    response = requests.get(part_url, headers=HEADERS)
    response.raise_for_status()
    
    soup = BeautifulSoup(response.content, 'html.parser')
    chapters = []
    
    content_div = soup.find('div', {'id': 'expandedbranchcodesid'})
    if not content_div:
        return chapters
    
    # Find all anchor tags that might contain chapters
    for anchor in content_div.find_all('a', href=True):
        href = anchor['href']
        
        # Look for divs within the anchor that have the chapter text
        chapter_div = anchor.find('div', style=lambda x: x and 'margin-left:30px' in x)
        if not chapter_div:
            continue
            
        link_text = chapter_div.get_text(strip=True)
        
        # Skip reserved chapters
        if '(Reserved)' in link_text:
            continue
        
        # Must contain "CHAPTER" in the text
        if 'CHAPTER' not in link_text.upper():
            continue
            
        parsed = urlparse(href)
        params = parse_qs(parsed.query)
        
        # Get chapter number
        chapter_num = params.get('chapter', [''])[0]
        if not chapter_num:
            continue
        
        # Get the range if it exists
        range_div = anchor.find('div', style=lambda x: x and 'float:right' in x)
        range_text = range_div.get_text(strip=True) if range_div else ""
        
        # Chapters can either be expandable (with articles) or direct content
        if 'codes_displayexpandedbranch.xhtml' in href:
            # This chapter has articles, needs to be expanded
            chapter_info = {
                'url': urljoin(BASE_URL, href),
                'title': link_text,
                'code': code,
                'division': division,
                'part': params.get('part', [''])[0],
                'chapter': chapter_num,
                'has_articles': True,
                'range': range_text,
                'articles': []
            }
            chapters.append(chapter_info)
            print(f"      Found chapter with articles: {link_text} ({range_text})")
        elif 'codes_displayText.xhtml' in href:
            # This chapter links directly to content
            chapter_info = {
                'url': urljoin(BASE_URL, href),
                'title': link_text,
                'code': code,
                'division': division,
                'part': params.get('part', [''])[0],
                'chapter': chapter_num,
                'has_articles': False,
                'range': range_text,
                'articles': []
            }
            chapters.append(chapter_info)
            print(f"      Found chapter with direct content: {link_text} ({range_text})")
    
    return chapters

def get_articles_for_chapter(chapter_url: str, code: str, division: str, part: str, chapter: str) -> List[Dict]:
    """Get all articles for a chapter that has expandable articles"""
    print(f"        Fetching articles from: {chapter_url}")
    response = requests.get(chapter_url, headers=HEADERS)
    response.raise_for_status()
    
    soup = BeautifulSoup(response.content, 'html.parser')
    articles = []
    
    content_div = soup.find('div', {'id': 'expandedbranchcodesid'})
    if not content_div:
        return articles
    
    # Find all anchor tags that might contain articles
    for anchor in content_div.find_all('a', href=True):
        href = anchor['href']
        
        # Look for divs within the anchor that have the article text
        article_div = anchor.find('div', style=lambda x: x and 'margin-left:40px' in x)
        if not article_div:
            continue
            
        link_text = article_div.get_text(strip=True)
        
        # Look for article links with actual content
        if 'codes_displayText.xhtml' in href and 'ARTICLE' in link_text.upper():
            parsed = urlparse(href)
            params = parse_qs(parsed.query)
            
            # Get the range if it exists
            range_div = anchor.find('div', style=lambda x: x and 'float:right' in x)
            range_text = range_div.get_text(strip=True) if range_div else ""
            
            article_info = {
                'url': urljoin(BASE_URL, href),
                'title': link_text,
                'code': code,
                'division': division,
                'part': params.get('part', [''])[0],
                'chapter': params.get('chapter', [''])[0],
                'article': params.get('article', [''])[0],
                'range': range_text
            }
            articles.append(article_info)
            print(f"          Found article: {link_text} ({range_text})")
    
    return articles

def parse_legal_code_html(soup: BeautifulSoup) -> str:
    """Parse California legal code HTML structure to extract formatted text"""
    output = []
    
    # Find the main content container
    main_div = soup.find('div', {'id': 'manylawsections'})
    if not main_div:
        main_div = soup.find('div', {'id': 'display_code_many_law_sections'})
        if not main_div:
            main_div = soup.find('div', class_='displaycodeleftmargin')
    
    if not main_div:
        return ""
    
    # Process headers (Code title, Division, Part info)
    headers = main_div.find_all(['h3', 'h4', 'h5'])
    for header in headers:
        header_text = header.get_text(strip=True)
        if header_text:
            output.append(header_text)
            
            # Look for citation info immediately after header
            next_elem = header.next_sibling
            while next_elem and isinstance(next_elem, str):
                next_elem = next_elem.next_sibling
            
            if next_elem and hasattr(next_elem, 'name'):
                if next_elem.name == 'i' or (next_elem.name == 'text' and next_elem.parent.name == 'i'):
                    citation_text = next_elem.get_text(strip=True)
                    if citation_text:
                        output.append(f"  {citation_text}")
            
            output.append("")  # Blank line after header
    
    # Process sections
    section_divs = main_div.find_all('div', {'align': 'left'})
    
    for div in section_divs:
        # Skip if this is a header div
        if div.find(['h3', 'h4', 'h5']):
            continue
            
        # Look for section number in h6 tag
        h6 = div.find('h6')
        if h6:
            # Extract section number
            section_link = h6.find('a')
            if section_link:
                section_num = section_link.get_text(strip=True).rstrip('.')
                
                # Only process if this looks like a section number
                if re.match(r'^\d+(?:\.\d+)*$', section_num):
                    output.append(f"\n{section_num}.")
                    
                    # Get all the p tags in this section div
                    p_tags = div.find_all('p')
                    
                    section_texts = []
                    citation_text = None
                    
                    for p in p_tags:
                        p_text = p.get_text(strip=True)
                        
                        if p_text:
                            # Check if this is a citation (has specific style or contains italic)
                            style = p.get('style', '')
                            if 'font-size:0.9em' in style or p.find('i'):
                                citation_text = p_text
                            elif 'display:inline' in style or 'margin:0' in style:
                                # This is regular section text
                                section_texts.append(p_text)
                    
                    # Combine section texts
                    if section_texts:
                        combined_text = ' '.join(section_texts)
                        # Remove section number if it appears at the start
                        combined_text = re.sub(f'^{section_num}\.?\\s*', '', combined_text)
                        output.append(f" {combined_text}")
                    
                    # Add citation if found
                    if citation_text:
                        output.append(f"\n{citation_text}")
    
    return '\n'.join(output)

def scrape_content(url: str) -> str:
    """Scrape content from a given URL"""
    response = requests.get(url, headers=HEADERS)
    response.raise_for_status()
    
    soup = BeautifulSoup(response.content, 'html.parser')
    
    # Use the specialized parser for legal code
    content_text = parse_legal_code_html(soup)
    
    return content_text

def create_filename(info: Dict) -> str:
    """Create a safe filename for the content"""
    code = info.get('code', 'unknown')
    division = info.get('division', 'unknown').replace('.', '_')
    part = info['part'].replace('.', '_') if info.get('part') else 'unknown'
    chapter = info.get('chapter', '').replace('.', '_') if info.get('chapter') else ''
    article = info.get('article', '').replace('.', '_') if info.get('article') else ''
    title = info['title']
    
    # Clean the title for use in filename
    title_clean = re.sub(r'[<>:"/\\|?*]', '_', title)
    title_clean = re.sub(r'\s+', '_', title_clean)
    title_clean = title_clean[:50]  # Limit length
    
    if article:
        filename = f"{code}_div{division}_part{part}_ch{chapter}_art{article}_{title_clean}.txt"
    elif chapter:
        filename = f"{code}_div{division}_part{part}_ch{chapter}_{title_clean}.txt"
    else:
        filename = f"{code}_div{division}_part{part}_{title_clean}.txt"
    
    return filename

def scrape_code_section(config: Dict) -> Tuple[int, int]:
    """Scrape a single code section based on configuration"""
    code = config['code']
    code_name = config['code_name']
    division = config['division']
    specific_parts = config.get('parts')
    
    print(f"\n{'='*60}")
    print(f"Processing {code_name} ({code}) - Division {division}")
    if specific_parts:
        print(f"Specific parts requested: {', '.join(specific_parts)}")
    print('='*60)
    
    # Create output directory
    output_dir = os.path.join(OUTPUT_BASE_DIR, f"{code}_division_{division}")
    os.makedirs(output_dir, exist_ok=True)
    
    # Get division structure
    print("Getting division structure...")
    parts = get_division_structure(code, division, specific_parts)
    
    if not parts:
        print("No parts found!")
        return 0, 0
    
    print(f"Found {len(parts)} parts to process")
    
    all_content = []
    successful_downloads = 0
    total_items = 0
    
    # Process each part
    for part_info in parts:
        print(f"\nProcessing Part {part_info['part']}: {part_info['title']}")
        
        if part_info['has_chapters']:
            # This part has chapters, need to expand it first
            print(f"  Expanding to get chapters...")
            chapters = get_chapters_for_part(part_info['url'], code, division, part_info['part'])
            
            if chapters:
                print(f"  Found {len(chapters)} chapters")
                part_info['chapters'] = chapters
                
                # Process each chapter
                for chapter in chapters:
                    if chapter.get('has_articles'):
                        # This chapter has articles, need to expand it
                        print(f"    Chapter {chapter['chapter']} has articles, expanding...")
                        articles = get_articles_for_chapter(chapter['url'], code, division, 
                                                          chapter['part'], chapter['chapter'])
                        
                        if articles:
                            print(f"      Found {len(articles)} articles")
                            chapter['articles'] = articles
                            
                            # Scrape each article
                            for article in articles:
                                total_items += 1
                                all_content.append(article)
                                
                                try:
                                    print(f"        Scraping article: {article['title'][:60]}...")
                                    content = scrape_content(article['url'])
                                    
                                    if content:
                                        filename = create_filename(article)
                                        filepath = os.path.join(output_dir, filename)
                                        
                                        with open(filepath, 'w', encoding='utf-8') as f:
                                            f.write(f"{code_name.upper()} - {code}\n")
                                            f.write(f"Division {article['division']}, Part {article['part']}, ")
                                            f.write(f"Chapter {article['chapter']}, Article {article['article']}\n")
                                            f.write(f"Title: {article['title']}\n")
                                            f.write(f"URL: {article['url']}\n")
                                            f.write("=" * 80 + "\n\n")
                                            f.write(content)
                                        
                                        print(f"          ✓ Saved: {filename}")
                                        successful_downloads += 1
                                    else:
                                        print(f"          ✗ No content found")
                                    
                                    time.sleep(REQUEST_DELAY)
                                    
                                except Exception as e:
                                    print(f"          ✗ Error: {str(e)}")
                        else:
                            print(f"      No articles found")
                    else:
                        # This chapter has direct content
                        total_items += 1
                        all_content.append(chapter)
                        
                        try:
                            print(f"    Scraping chapter: {chapter['title'][:60]}...")
                            content = scrape_content(chapter['url'])
                            
                            if content:
                                filename = create_filename(chapter)
                                filepath = os.path.join(output_dir, filename)
                                
                                with open(filepath, 'w', encoding='utf-8') as f:
                                    f.write(f"{code_name.upper()} - {code}\n")
                                    f.write(f"Division {chapter['division']}, Part {chapter['part']}, Chapter {chapter['chapter']}\n")
                                    f.write(f"Title: {chapter['title']}\n")
                                    f.write(f"URL: {chapter['url']}\n")
                                    f.write("=" * 80 + "\n\n")
                                    f.write(content)
                                
                                print(f"      ✓ Saved: {filename}")
                                successful_downloads += 1
                            else:
                                print(f"      ✗ No content found")
                            
                            time.sleep(REQUEST_DELAY)
                            
                        except Exception as e:
                            print(f"      ✗ Error: {str(e)}")
            else:
                print(f"  No chapters found for this part")
        else:
            # This part links directly to content (no chapters)
            total_items += 1
            all_content.append(part_info)
            
            try:
                print(f"  Scraping part directly (no chapters)...")
                content = scrape_content(part_info['url'])
                
                if content:
                    filename = create_filename(part_info)
                    filepath = os.path.join(output_dir, filename)
                    
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(f"{code_name.upper()} - {code}\n")
                        f.write(f"Division {part_info['division']}, Part {part_info['part']}\n")
                        f.write(f"Title: {part_info['title']}\n")
                        f.write(f"URL: {part_info['url']}\n")
                        f.write("=" * 80 + "\n\n")
                        f.write(content)
                    
                    print(f"    ✓ Saved: {filename}")
                    successful_downloads += 1
                else:
                    print(f"    ✗ No content found")
                
                time.sleep(REQUEST_DELAY)
                
            except Exception as e:
                print(f"    ✗ Error: {str(e)}")
    
    # Save the structure for this code section
    structure_file = os.path.join(output_dir, f"{code}_division_{division}_structure.json")
    with open(structure_file, 'w', encoding='utf-8') as f:
        json.dump(parts, f, indent=2, ensure_ascii=False)
    
    print(f"\nStructure saved to {structure_file}")
    
    return successful_downloads, total_items

def main():
    """Main function to scrape all configured code sections"""
    
    # Create base output directory
    os.makedirs(OUTPUT_BASE_DIR, exist_ok=True)
    
    print("California Legal Code Scraper")
    print("=" * 60)
    print(f"Configuration:")
    print(f"  - Output directory: {OUTPUT_BASE_DIR}")
    print(f"  - Request delay: {REQUEST_DELAY} seconds")
    print(f"  - Code sections to scrape: {len(CODE_SECTIONS_TO_SCRAPE)}")
    
    total_successful = 0
    total_items = 0
    
    # Process each configured code section
    for config in CODE_SECTIONS_TO_SCRAPE:
        successful, items = scrape_code_section(config)
        total_successful += successful
        total_items += items
    
    # Final summary
    print(f"\n{'='*60}")
    print(f"SCRAPING COMPLETE!")
    print(f"Total items found: {total_items}")
    print(f"Successfully downloaded: {total_successful}/{total_items}")
    print(f"Files saved to {OUTPUT_BASE_DIR}/")

if __name__ == "__main__":
    main()