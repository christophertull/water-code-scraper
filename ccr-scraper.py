import requests
from bs4 import BeautifulSoup
import re
import os
import time
from urllib.parse import urljoin, urlparse
import json
from pathlib import Path

class CaliforniaRegulationsScraper:
    def __init__(self, output_dir="ca_regs_chapter_3_5"):
        self.base_url = "https://shared-govt.westlaw.com"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        self.output_dir = Path(output_dir)
        self.images_dir = self.output_dir / "images"
        self.output_dir.mkdir(exist_ok=True)
        self.images_dir.mkdir(exist_ok=True)
        
    def get_page_content(self, url):
        """Fetch page content with error handling"""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return BeautifulSoup(response.content, 'html.parser')
        except Exception as e:
            print(f"Error fetching {url}: {str(e)}")
            return None
    
    def extract_articles_from_chapter(self, chapter_url):
        """Extract all article links from the chapter page"""
        soup = self.get_page_content(chapter_url)
        if not soup:
            return []
        
        articles = []
        # Find the list of articles
        article_list = soup.find('ul', class_='co_genericWhiteBox')
        if not article_list:
            print("Could not find article list")
            return []
        
        for li in article_list.find_all('li'):
            link = li.find('a')
            if link and link.get('href'):
                article_info = {
                    'title': link.get_text(strip=True),
                    'url': urljoin(self.base_url, link['href']),
                    'sections': []
                }
                articles.append(article_info)
        
        return articles
    
    def extract_sections_from_article(self, article_url):
        """Extract all section links from an article page"""
        soup = self.get_page_content(article_url)
        if not soup:
            return []
        
        sections = []
        # Find the list of sections
        section_list = soup.find('ul', class_='co_genericWhiteBox')
        if not section_list:
            print("Could not find section list")
            return []
        
        for li in section_list.find_all('li'):
            link = li.find('a')
            if link and link.get('href'):
                section_info = {
                    'title': link.get_text(strip=True),
                    'url': urljoin(self.base_url, link['href'])
                }
                sections.append(section_info)
        
        return sections
    
    def convert_subscripts_to_text(self, element):
        """Convert HTML subscripts to underscore notation for LLM understanding"""
        # Find all subscript tags and replace them
        for sub in element.find_all('sub'):
            sub_text = sub.get_text()
            sub.replace_with(f"_{sub_text}")
        
        # Find all superscript tags and replace them
        for sup in element.find_all('sup'):
            sup_text = sup.get_text()
            sup.replace_with(f"^{sup_text}")
        
        return element
    
    def download_image(self, img_url, section_title):
        """Download and save an image, return local filename"""
        try:
            # Clean the section title for filename
            clean_title = re.sub(r'[<>:"/\\|?*§.]', '_', section_title)
            clean_title = re.sub(r'\s+', '_', clean_title)
            
            # Parse the image URL to get the original filename
            parsed_url = urlparse(img_url)
            img_name = parsed_url.path.split('/')[-1]
            if not img_name or '.' not in img_name:
                img_name = "formula.png"
            
            # Create a descriptive filename
            local_filename = f"{clean_title}_{img_name}"
            local_path = self.images_dir / local_filename
            
            # Download the image
            response = self.session.get(img_url, timeout=30)
            response.raise_for_status()
            
            with open(local_path, 'wb') as f:
                f.write(response.content)
            
            print(f"    Downloaded image: {local_filename}")
            return local_filename
            
        except Exception as e:
            print(f"    Error downloading image {img_url}: {str(e)}")
            return None
    
    def process_mathematical_images(self, soup, section_title):
        """Find and download mathematical formula images"""
        images_downloaded = []
        
        # Look for images in figure blocks or mathematical contexts
        for img in soup.find_all('img'):
            img_src = img.get('src')
            if img_src:
                # Convert relative URLs to absolute
                if img_src.startswith('/'):
                    img_url = urljoin("https://govt.westlaw.com", img_src)
                elif img_src.startswith('http'):
                    img_url = img_src
                else:
                    img_url = urljoin(self.base_url, img_src)
                
                # Check if this looks like a mathematical formula
                # (could be in a figure block, or have mathematical alt text)
                img_alt = img.get('alt', '').lower()
                parent_class = img.parent.get('class', []) if img.parent else []
                
                if (any('figure' in cls for cls in parent_class) or 
                    'formula' in img_alt or 'equation' in img_alt or 
                    any(word in img_alt for word in ['sum', 'equals', 'water loss'])):
                    
                    local_filename = self.download_image(img_url, section_title)
                    if local_filename:
                        images_downloaded.append({
                            'original_url': img_url,
                            'local_file': local_filename,
                            'alt_text': img.get('alt', ''),
                            'description': f"Mathematical formula from {section_title}"
                        })
                        
                        # Replace the image with a text reference
                        img.replace_with(f"\n[IMAGE: {local_filename} - {img.get('alt', 'Mathematical formula')}]\n")
        
        return images_downloaded
    
    def extract_section_content(self, section_url, section_title):
        """Extract the main content from a section page"""
        soup = self.get_page_content(section_url)
        if not soup:
            return "", []
        
        # Process mathematical images first
        images = self.process_mathematical_images(soup, section_title)
        
        # Find the main document content
        doc_content = soup.find('div', {'id': 'co_document'})
        if not doc_content:
            print(f"Could not find document content for {section_title}")
            return "", images
        
        # Extract the title and citation info
        title_section = soup.find('div', {'id': 'co_docHeaderTitle'})
        content_lines = []
        
        if title_section:
            title_h1 = title_section.find('h1')
            if title_h1:
                title_text = title_h1.get_text(strip=True)
                content_lines.append(title_text)
                content_lines.append("=" * len(title_text))
                content_lines.append("")
            
            # Get citation info
            citation_ul = title_section.find('ul', {'id': 'co_docHeaderCitation'})
            if citation_ul:
                for li in citation_ul.find_all('li'):
                    citation_text = li.get_text(strip=True)
                    if citation_text:
                        content_lines.append(citation_text)
                content_lines.append("")
        
        # Extract the main content sections
        content_blocks = doc_content.find_all('div', class_='co_contentBlock')
        
        for block in content_blocks:
            # Skip certain types of blocks
            if any(cls in block.get('class', []) for cls in ['co_documentHead', 'co_printHeading']):
                continue
            
            # Convert subscripts and superscripts
            block = self.convert_subscripts_to_text(block)
            
            # Handle different types of content blocks
            if 'co_section' in block.get('class', []):
                self.process_section_block(block, content_lines)
            elif 'co_subsection' in block.get('class', []):
                self.process_subsection_block(block, content_lines)
            elif 'co_paragraph' in block.get('class', []):
                self.process_paragraph_block(block, content_lines)
            else:
                # Generic text extraction
                text = block.get_text(strip=True)
                if text and not text.startswith(('Note:', 'History:', 'Credits')):
                    content_lines.append(text)
                    content_lines.append("")
        
        return "\n".join(content_lines), images
    
    def process_section_block(self, block, content_lines):
        """Process a section-level content block"""
        # Look for subsection identifiers like (a), (b), etc.
        paragraphs = block.find_all('div', class_='co_paragraph')
        
        for para in paragraphs:
            para_text = para.get_text(strip=True)
            if para_text:
                # Check if this starts with a subsection identifier
                if re.match(r'^\([a-z]\)', para_text):
                    content_lines.append("")  # Add space before new subsection
                content_lines.append(para_text)
        
        content_lines.append("")
    
    def process_subsection_block(self, block, content_lines):
        """Process a subsection-level content block"""
        text = block.get_text(strip=True)
        if text:
            content_lines.append(text)
            content_lines.append("")
    
    def process_paragraph_block(self, block, content_lines):
        """Process a paragraph-level content block"""
        text = block.get_text(strip=True)
        if text:
            content_lines.append(text)
    
    def create_safe_filename(self, title):
        """Create a safe filename from a title"""
        # Remove section symbol and clean up
        clean_title = re.sub(r'[§<>:"/\\|?*]', '', title)
        clean_title = re.sub(r'\s+', '_', clean_title.strip())
        # Limit length
        if len(clean_title) > 100:
            clean_title = clean_title[:100]
        return clean_title
    
    def scrape_chapter_3_5(self, chapter_url):
        """Main method to scrape Chapter 3.5"""
        print("Starting scrape of Chapter 3.5: Urban Water Use Efficiency and Conservation")
        
        # Get all articles in the chapter
        articles = self.extract_articles_from_chapter(chapter_url)
        print(f"Found {len(articles)} articles")
        
        all_images = []
        scraping_log = {
            'chapter_title': 'Chapter 3.5. Urban Water Use Efficiency and Conservation',
            'chapter_url': chapter_url,
            'articles': [],
            'total_sections': 0,
            'images_downloaded': 0
        }
        
        for i, article in enumerate(articles, 1):
            print(f"\nProcessing Article {i}: {article['title']}")
            
            # Get all sections in this article
            sections = self.extract_sections_from_article(article['url'])
            article['sections'] = sections
            print(f"  Found {len(sections)} sections")
            
            article_info = {
                'title': article['title'],
                'url': article['url'],
                'sections': []
            }
            
            for j, section in enumerate(sections, 1):
                print(f"    Processing Section {j}: {section['title']}")
                
                # Extract content from this section
                content, images = self.extract_section_content(section['url'], section['title'])
                
                if content:
                    # Save individual section file
                    filename = f"article_{i}_section_{j}_{self.create_safe_filename(section['title'])}.txt"
                    filepath = self.output_dir / filename
                    
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(f"CALIFORNIA CODE OF REGULATIONS\n")
                        f.write(f"Title 23. Waters\n")
                        f.write(f"Division 3. State Water Resources Control Board and Regional Water Quality Control Boards\n")
                        f.write(f"Chapter 3.5. Urban Water Use Efficiency and Conservation\n")
                        f.write(f"Article {i}: {article['title']}\n")
                        f.write(f"URL: {section['url']}\n")
                        f.write("=" * 80 + "\n\n")
                        f.write(content)
                    
                    print(f"      ✓ Saved: {filename}")
                    
                    # Track images
                    all_images.extend(images)
                    
                    section_info = {
                        'title': section['title'],
                        'url': section['url'],
                        'filename': filename,
                        'images': [img['local_file'] for img in images]
                    }
                    article_info['sections'].append(section_info)
                    scraping_log['total_sections'] += 1
                    
                else:
                    print(f"      ✗ No content extracted")
                
                time.sleep(1)  # Be respectful to the server
            
            scraping_log['articles'].append(article_info)
        
        # Save metadata and image information
        scraping_log['images_downloaded'] = len(all_images)
        
        # Save scraping log
        log_file = self.output_dir / "scraping_log.json"
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(scraping_log, f, indent=2, ensure_ascii=False)
        
        # Save image metadata
        if all_images:
            images_file = self.output_dir / "images_metadata.json"
            with open(images_file, 'w', encoding='utf-8') as f:
                json.dump(all_images, f, indent=2, ensure_ascii=False)
        
        print(f"\n{'='*60}")
        print(f"Scraping complete!")
        print(f"Total articles: {len(articles)}")
        print(f"Total sections: {scraping_log['total_sections']}")
        print(f"Images downloaded: {len(all_images)}")
        print(f"Files saved to: {self.output_dir}")

def main():
    # URL for Chapter 3.5
    chapter_url = "https://shared-govt.westlaw.com/calregs/Browse/Home/California/CaliforniaCodeofRegulations?guid=IC6CFA5735B6E11EC9451000D3A7C4BC3&originationContext=documenttoc&transitionType=Default&contextData=(sc.Default)"
    
    scraper = CaliforniaRegulationsScraper()
    scraper.scrape_chapter_3_5(chapter_url)

if __name__ == "__main__":
    main()