"""
Statute Fetcher Service

Fetches current statute text from official government sources:
- USC (United States Code) from govinfo.gov
- CFR (Code of Federal Regulations) from eCFR.gov
"""

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Tuple
from bs4 import BeautifulSoup

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class FetchedStatute:
    """Result of fetching a statute."""
    citation_type: str  # usc, cfr
    title: int
    section: str
    heading: Optional[str]
    full_text: str
    source_url: str
    success: bool
    error_message: Optional[str] = None


class StatuteFetcher(ABC):
    """Base class for statute fetchers."""

    @abstractmethod
    async def fetch(self, title: int, section: str) -> FetchedStatute:
        """Fetch statute text for the given title and section."""
        pass

    def _clean_text(self, text: str) -> str:
        """Clean up extracted text."""
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        # Remove leading/trailing whitespace from lines
        lines = [line.strip() for line in text.split('\n')]
        # Remove empty lines
        lines = [line for line in lines if line]
        return '\n'.join(lines)


class GovInfoFetcher(StatuteFetcher):
    """
    Fetches USC sections from govinfo.gov using the Link Service.

    URL Pattern: https://www.govinfo.gov/link/uscode/{title}/{section}
    Optional params: year, type (usc/uscappendix), link-type (pdf/html)

    Note: For HTML content, we use link-type=html and parse the response.
    """

    BASE_URL = "https://www.govinfo.gov/link/uscode"
    TIMEOUT = 30.0

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.GOVINFO_API_KEY

    async def fetch(self, title: int, section: str) -> FetchedStatute:
        """Fetch USC section from govinfo.gov."""
        # Clean section - remove any subsection notation for the URL
        base_section = section.split('(')[0].strip()

        # Construct URL
        url = f"{self.BASE_URL}/{title}/{base_section}"
        params = {
            "link-type": "html",
            "year": "mostrecent",
        }
        if self.api_key:
            params["api_key"] = self.api_key

        source_url = f"{url}?link-type=html"

        try:
            async with httpx.AsyncClient(timeout=self.TIMEOUT, follow_redirects=True) as client:
                response = await client.get(url, params=params)

                if response.status_code == 404:
                    return FetchedStatute(
                        citation_type="usc",
                        title=title,
                        section=section,
                        heading=None,
                        full_text="",
                        source_url=source_url,
                        success=False,
                        error_message=f"Section not found: {title} U.S.C. § {section}"
                    )

                if response.status_code != 200:
                    return FetchedStatute(
                        citation_type="usc",
                        title=title,
                        section=section,
                        heading=None,
                        full_text="",
                        source_url=source_url,
                        success=False,
                        error_message=f"HTTP {response.status_code}: {response.reason_phrase}"
                    )

                # Parse HTML content
                heading, text = self._parse_usc_html(response.text)

                if not text:
                    return FetchedStatute(
                        citation_type="usc",
                        title=title,
                        section=section,
                        heading=heading,
                        full_text="",
                        source_url=source_url,
                        success=False,
                        error_message="Could not extract text from response"
                    )

                logger.info(f"Successfully fetched {title} U.S.C. § {section}")

                return FetchedStatute(
                    citation_type="usc",
                    title=title,
                    section=section,
                    heading=heading,
                    full_text=text,
                    source_url=str(response.url),
                    success=True
                )

        except httpx.TimeoutException:
            logger.error(f"Timeout fetching {title} U.S.C. § {section}")
            return FetchedStatute(
                citation_type="usc",
                title=title,
                section=section,
                heading=None,
                full_text="",
                source_url=source_url,
                success=False,
                error_message="Request timed out"
            )
        except Exception as e:
            logger.error(f"Error fetching {title} U.S.C. § {section}: {e}")
            return FetchedStatute(
                citation_type="usc",
                title=title,
                section=section,
                heading=None,
                full_text="",
                source_url=source_url,
                success=False,
                error_message=str(e)
            )

    def _parse_usc_html(self, html: str) -> Tuple[Optional[str], str]:
        """
        Parse USC HTML from govinfo.gov and extract ONLY operative statute text.

        GovInfo HTML structure:
        - <!-- field-start:statute --> marks start of operative law
        - <!-- field-end:statute --> marks end of operative law
        - Everything after (sourcecredit, notes, amendments) is historical metadata
        """
        soup = BeautifulSoup(html, 'html.parser')

        # Try to find the section heading
        heading = None
        heading_elem = soup.find('h3', class_='section-head')
        if heading_elem:
            heading = heading_elem.get_text(strip=True)

        # Extract ONLY the operative statute text between the HTML comments
        # The comments mark: <!-- field-start:statute --> and <!-- field-end:statute -->
        statute_text = self._extract_statute_section(html)

        if statute_text:
            # Parse the extracted statute section for structured output
            statute_soup = BeautifulSoup(statute_text, 'html.parser')
            formatted_text = self._format_statute_text(statute_soup)
            return heading, formatted_text

        # Fallback: try to find content by class names (less reliable)
        return heading, self._fallback_parse(soup)

    def _extract_statute_section(self, html: str) -> Optional[str]:
        """Extract only the operative statute text between field markers."""
        # Look for the statute section markers in the HTML
        start_marker = '<!-- field-start:statute -->'
        end_marker = '<!-- field-end:statute -->'

        start_idx = html.find(start_marker)
        end_idx = html.find(end_marker)

        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            # Extract content between markers
            return html[start_idx + len(start_marker):end_idx]

        return None

    def _format_statute_text(self, soup: BeautifulSoup) -> str:
        """
        Format statute text with clear hierarchy for human readability.

        Output format:
        (a) IN GENERAL
            (1) First paragraph text...
            (2) Second paragraph text...
                (A) Subparagraph text...
        """
        lines = []

        for elem in soup.find_all(['h4', 'p'], recursive=True):
            class_name = ' '.join(elem.get('class', []))
            text = elem.get_text(separator=' ', strip=True)

            if not text:
                continue

            # Determine indentation based on element type
            if 'subsection-head' in class_name:
                # Main subsection header: (a) In general
                lines.append(f"\n{text}")
            elif 'paragraph-head' in class_name:
                # Paragraph header: (1) Eligibility requirements
                lines.append(f"\n    {text}")
            elif 'subparagraph-head' in class_name:
                # Subparagraph header: (A) Special rule
                lines.append(f"\n        {text}")
            elif 'statutory-body' in class_name and '1em' in class_name:
                # Paragraph body text (1em indent)
                lines.append(f"    {text}")
            elif 'statutory-body' in class_name and '2em' in class_name:
                # Subparagraph body text (2em indent)
                lines.append(f"        {text}")
            elif 'statutory-body' in class_name and '3em' in class_name:
                # Clause body text (3em indent)
                lines.append(f"            {text}")
            elif 'statutory-body' in class_name:
                # Default statutory body
                lines.append(f"    {text}")
            elif elem.name == 'p' and text:
                # Generic paragraph
                lines.append(f"    {text}")

        return '\n'.join(lines).strip()

    def _fallback_parse(self, soup: BeautifulSoup) -> str:
        """Fallback parser when field markers aren't found."""
        # Try to find statute content by class names
        text_parts = []

        # Look for elements with statute-related classes
        for class_pattern in ['subsection-head', 'paragraph-head', 'statutory-body']:
            for elem in soup.find_all(class_=lambda c: c and class_pattern in ' '.join(c) if c else False):
                text = elem.get_text(separator=' ', strip=True)
                if text and len(text) > 10:
                    text_parts.append(text)

        if text_parts:
            return '\n\n'.join(text_parts)

        # Last resort: get body text but exclude known junk
        body = soup.body or soup
        for junk in body.find_all(['script', 'style', 'nav', 'footer']):
            junk.decompose()

        # Also remove source-credit and notes sections
        for elem in body.find_all(class_=lambda c: c and any(x in ' '.join(c) for x in ['source-credit', 'note']) if c else False):
            elem.decompose()

        return self._clean_text(body.get_text(separator='\n', strip=True))


class ECFRFetcher(StatuteFetcher):
    """
    Fetches CFR sections from eCFR.gov.

    The eCFR API provides access to the Code of Federal Regulations.
    Base URL: https://www.ecfr.gov

    Section URL pattern: /current/title-{title}/section-{section}

    Note: eCFR API may be unavailable during government shutdowns.
    """

    BASE_URL = "https://www.ecfr.gov"
    API_BASE = "https://www.ecfr.gov/api/versioner/v1"
    TIMEOUT = 30.0

    async def fetch(self, title: int, section: str) -> FetchedStatute:
        """Fetch CFR section from eCFR.gov."""
        # For CFR, sections are formatted like "482.12" for 42 CFR 482.12
        # The URL pattern is /current/title-{title}/section-{section}

        # Construct URLs
        html_url = f"{self.BASE_URL}/current/title-{title}/section-{section}"
        source_url = html_url

        try:
            async with httpx.AsyncClient(timeout=self.TIMEOUT, follow_redirects=True) as client:
                # Try fetching the HTML page directly
                response = await client.get(html_url)

                # Check for redirects to blocking page (government shutdown)
                if "unblock.federalregister.gov" in str(response.url):
                    return FetchedStatute(
                        citation_type="cfr",
                        title=title,
                        section=section,
                        heading=None,
                        full_text="",
                        source_url=source_url,
                        success=False,
                        error_message="eCFR.gov is currently unavailable (government operations suspended)"
                    )

                if response.status_code == 404:
                    return FetchedStatute(
                        citation_type="cfr",
                        title=title,
                        section=section,
                        heading=None,
                        full_text="",
                        source_url=source_url,
                        success=False,
                        error_message=f"Section not found: {title} C.F.R. § {section}"
                    )

                if response.status_code != 200:
                    return FetchedStatute(
                        citation_type="cfr",
                        title=title,
                        section=section,
                        heading=None,
                        full_text="",
                        source_url=source_url,
                        success=False,
                        error_message=f"HTTP {response.status_code}: {response.reason_phrase}"
                    )

                # Parse HTML content
                heading, text = self._parse_ecfr_html(response.text)

                if not text:
                    return FetchedStatute(
                        citation_type="cfr",
                        title=title,
                        section=section,
                        heading=heading,
                        full_text="",
                        source_url=source_url,
                        success=False,
                        error_message="Could not extract text from response"
                    )

                logger.info(f"Successfully fetched {title} C.F.R. § {section}")

                return FetchedStatute(
                    citation_type="cfr",
                    title=title,
                    section=section,
                    heading=heading,
                    full_text=text,
                    source_url=str(response.url),
                    success=True
                )

        except httpx.TimeoutException:
            logger.error(f"Timeout fetching {title} C.F.R. § {section}")
            return FetchedStatute(
                citation_type="cfr",
                title=title,
                section=section,
                heading=None,
                full_text="",
                source_url=source_url,
                success=False,
                error_message="Request timed out"
            )
        except Exception as e:
            logger.error(f"Error fetching {title} C.F.R. § {section}: {e}")
            return FetchedStatute(
                citation_type="cfr",
                title=title,
                section=section,
                heading=None,
                full_text="",
                source_url=source_url,
                success=False,
                error_message=str(e)
            )

    def _parse_ecfr_html(self, html: str) -> Tuple[Optional[str], str]:
        """Parse eCFR HTML and extract heading and text."""
        soup = BeautifulSoup(html, 'html.parser')

        # Find section heading
        heading = None
        heading_elem = soup.find('h1', class_='section-head') or soup.find('h1')
        if heading_elem:
            heading = heading_elem.get_text(strip=True)

        # Find the main regulation content
        content = None
        for selector in [
            'div.section-content',
            'div[data-section]',
            'div.ecfr-content',
            'article',
            'main',
        ]:
            content = soup.select_one(selector)
            if content:
                break

        if not content:
            content = soup.body or soup

        # Extract paragraphs
        text_parts = []
        for elem in content.find_all(['p', 'div'], recursive=True):
            # Skip navigation and metadata elements
            if elem.get('class') and any(c in str(elem.get('class')) for c in ['nav', 'meta', 'header', 'footer']):
                continue
            text = elem.get_text(separator=' ', strip=True)
            if text and len(text) > 20:
                text_parts.append(text)

        # Deduplicate
        seen = set()
        unique_parts = []
        for part in text_parts:
            if part not in seen:
                seen.add(part)
                unique_parts.append(part)

        full_text = '\n\n'.join(unique_parts)

        return heading, self._clean_text(full_text)


class StatuteFetcherService:
    """
    Main service for fetching statutes from appropriate sources.

    Usage:
        service = StatuteFetcherService()
        result = await service.fetch("usc", 26, "501")
        if result.success:
            print(result.full_text)
    """

    def __init__(self):
        self.usc_fetcher = GovInfoFetcher()
        self.cfr_fetcher = ECFRFetcher()

    async def fetch(self, citation_type: str, title: int, section: str) -> FetchedStatute:
        """
        Fetch statute text based on citation type.

        Args:
            citation_type: "usc" or "cfr"
            title: Title number (e.g., 26 for 26 U.S.C.)
            section: Section number (e.g., "501" or "482.12")

        Returns:
            FetchedStatute with the result
        """
        citation_type = citation_type.lower()

        if citation_type == "usc":
            return await self.usc_fetcher.fetch(title, section)
        elif citation_type == "cfr":
            return await self.cfr_fetcher.fetch(title, section)
        else:
            return FetchedStatute(
                citation_type=citation_type,
                title=title,
                section=section,
                heading=None,
                full_text="",
                source_url="",
                success=False,
                error_message=f"Unsupported citation type: {citation_type}"
            )
