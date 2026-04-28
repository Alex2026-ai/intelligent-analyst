"""
Person Canonical Loader

Loader for externally supplied person reference data.
No reference dataset is embedded in this public repository.

NO EMBEDDED DATA - All reference data must be loaded from external sources.

Multi-source support:
- PERSON_WATCHLIST_SOURCES=ofac,un,eu
- Automatic deduplication by normalized name + DOB
- Source evidence preserved for compliance
"""

import os
import json
import csv
import re
import hashlib
import unicodedata
from typing import Dict, List, Set, Optional, Tuple
from collections import defaultdict
from xml.etree import ElementTree as ET


class PersonCanonicalStore:
    """
    In-memory store for person canonicals with pre-built indexes.

    Multi-source support:
    - Records can have multiple sources (OFAC, UN, EU)
    - Sources tracked per record for compliance evidence
    - Deduplication by normalized name + DOB

    Indexes:
    - canonical_set: normalized names for O(1) exact lookup
    - normalized_lookup: normalized name -> full record
    - alias_lookup: alias (normalized) -> full record
    - last_name_index: last_name -> [records]
    - id_lookup: id -> full record
    """

    def __init__(self):
        self.persons: List[Dict] = []
        self.canonical_set: Set[str] = set()
        self.normalized_lookup: Dict[str, Dict] = {}
        self.alias_lookup: Dict[str, Dict] = {}
        self.last_name_index: Dict[str, List[Dict]] = defaultdict(list)
        self.id_lookup: Dict[str, Dict] = {}
        self.source: str = "none"
        self.sources_loaded: List[str] = []  # List of sources loaded
        self.source_counts: Dict[str, int] = {}  # Count per source
        self.record_count: int = 0
        self.version_hash: str = ""  # SHA256 of all source files

    @staticmethod
    def normalize_for_index(name: str) -> str:
        """
        Normalize a name for index lookup.
        - Lowercase
        - Remove accents/diacritics
        - Handle "LAST, FIRST" format -> "first last"
        - Remove punctuation except apostrophe
        - Collapse whitespace
        """
        if not name:
            return ""

        # Lowercase
        name = str(name).lower().strip()

        # Remove accents (NFKD decomposition)
        name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('ascii')

        # Handle "LAST, FIRST" format - reorder to "first last"
        if ',' in name:
            parts = name.split(',', 1)
            if len(parts) == 2:
                last = parts[0].strip()
                first = parts[1].strip()
                name = f"{first} {last}"

        # Remove punctuation except apostrophe (O'Brien)
        name = re.sub(r"[^\w\s']", ' ', name)

        # Collapse whitespace
        name = ' '.join(name.split())

        return name

    def build_indexes(self, persons: List[Dict], source: str) -> None:
        """Build lookup indexes from person list."""
        # Clear existing indexes
        self.persons = persons
        self.canonical_set = set()
        self.normalized_lookup = {}
        self.alias_lookup = {}
        self.last_name_index = defaultdict(list)
        self.id_lookup = {}
        self.source = source
        self.record_count = len(persons)

        for person in persons:
            # Index by ID
            person_id = person.get("id", "")
            if person_id:
                self.id_lookup[person_id] = person

            # Index by normalized canonical name
            canonical = person.get("canonical_name", "")
            if canonical:
                normalized = self.normalize_for_index(canonical)
                self.canonical_set.add(normalized)
                self.normalized_lookup[normalized] = person

            # Index aliases
            for alias in person.get("aliases", []):
                alias_norm = self.normalize_for_index(alias)
                if alias_norm and alias_norm not in self.alias_lookup:
                    self.alias_lookup[alias_norm] = person

            # Index by last name
            last_name = person.get("last_name", "")
            if last_name:
                last_norm = self.normalize_for_index(last_name)
                self.last_name_index[last_norm].append(person)

        print(f"[PERSON_CANONICALS] Built indexes: {self.record_count} persons, "
              f"{len(self.alias_lookup)} aliases, {len(self.last_name_index)} last names", flush=True)

    def get_by_id(self, person_id: str) -> Optional[Dict]:
        """Get a person record by ID."""
        return self.id_lookup.get(person_id)

    def get_exact_match(self, normalized_name: str) -> Optional[Dict]:
        """Check for exact match in canonical set."""
        return self.normalized_lookup.get(normalized_name)

    def get_alias_match(self, normalized_name: str) -> Optional[Dict]:
        """Check for alias match."""
        return self.alias_lookup.get(normalized_name)

    def get_candidates_by_last_name(self, last_name: str) -> List[Dict]:
        """Get all persons with a given last name."""
        last_norm = self.normalize_for_index(last_name)
        return self.last_name_index.get(last_norm, [])

    def get_all_persons(self) -> List[Dict]:
        """Get all person canonicals."""
        return self.persons

    def is_loaded(self) -> bool:
        """Check if any data is loaded."""
        return self.record_count > 0


class PersonCanonicalLoader:
    """
    Loader for person canonicals from various sources.

    Supported sources:
    - Firestore: load_from_firestore(collection_name)
    - CSV: load_from_csv(filepath)
    - JSON: load_from_json(filepath)
    """

    def __init__(self):
        self.store = PersonCanonicalStore()

    def load_from_firestore(self, collection_name: str = "person_canonicals") -> PersonCanonicalStore:
        """
        Load person canonicals from Firestore.

        Expected document structure:
        {
            "id": "SDN-12345",
            "canonical_name": "LASTNAME, Firstname Middlename",
            "aliases": ["alias1", "alias2"],
            "first_name": "Firstname",
            "last_name": "LASTNAME",
            "patronymic": "Middlename",
            "source": "OFAC_SDN",
            "metadata": {"dob": "1970-01-01", "nationality": "XX"}
        }
        """
        try:
            from google.cloud import firestore

            project_id = os.getenv("GCP_PROJECT_ID", "intelligent-analyst-enterprise")
            db = firestore.Client(project=project_id)

            print(f"[PERSON_CANONICALS] Loading from Firestore collection: {collection_name}", flush=True)

            docs = db.collection(collection_name).stream()
            persons = []

            for doc in docs:
                person = doc.to_dict()
                person["id"] = doc.id  # Use document ID if not in data
                persons.append(person)

            self.store.build_indexes(persons, f"firestore:{collection_name}")
            print(f"[PERSON_CANONICALS] Loaded {len(persons)} records from Firestore", flush=True)

            return self.store

        except Exception as e:
            print(f"[PERSON_CANONICALS] Failed to load from Firestore: {e}", flush=True)
            return self.store

    def load_from_json(self, filepath: str) -> PersonCanonicalStore:
        """
        Load person canonicals from a JSON file.

        Expected format:
        [
            {
                "id": "SDN-12345",
                "canonical_name": "LASTNAME, Firstname Middlename",
                "aliases": ["alias1", "alias2"],
                ...
            },
            ...
        ]
        """
        try:
            print(f"[PERSON_CANONICALS] Loading from JSON: {filepath}", flush=True)

            with open(filepath, 'r', encoding='utf-8') as f:
                persons = json.load(f)

            if not isinstance(persons, list):
                print(f"[PERSON_CANONICALS] JSON must be a list of person records", flush=True)
                return self.store

            self.store.build_indexes(persons, f"json:{filepath}")
            print(f"[PERSON_CANONICALS] Loaded {len(persons)} records from JSON", flush=True)

            return self.store

        except Exception as e:
            print(f"[PERSON_CANONICALS] Failed to load from JSON: {e}", flush=True)
            return self.store

    def load_from_csv(self, filepath: str) -> PersonCanonicalStore:
        """
        Load person canonicals from a CSV file.

        Expected columns:
        - id: Unique identifier
        - canonical_name: Full canonical name
        - aliases: Pipe-separated list (e.g., "alias1|alias2")
        - first_name: First name
        - last_name: Last name
        - patronymic: Patronymic (optional)
        - source: Data source (e.g., OFAC_SDN, UN_CONSOLIDATED)
        - dob: Date of birth (optional)
        - nationality: Country code (optional)
        """
        try:
            print(f"[PERSON_CANONICALS] Loading from CSV: {filepath}", flush=True)

            persons = []
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)

                for row in reader:
                    # Parse aliases from pipe-separated string
                    aliases_str = row.get("aliases", "")
                    aliases = [a.strip() for a in aliases_str.split("|") if a.strip()]

                    person = {
                        "id": row.get("id", ""),
                        "canonical_name": row.get("canonical_name", ""),
                        "aliases": aliases,
                        "first_name": row.get("first_name", ""),
                        "last_name": row.get("last_name", ""),
                        "patronymic": row.get("patronymic", ""),
                        "source": row.get("source", "CSV"),
                        "metadata": {
                            "dob": row.get("dob", ""),
                            "nationality": row.get("nationality", "")
                        }
                    }
                    persons.append(person)

            self.store.build_indexes(persons, f"csv:{filepath}")
            print(f"[PERSON_CANONICALS] Loaded {len(persons)} records from CSV", flush=True)

            return self.store

        except Exception as e:
            print(f"[PERSON_CANONICALS] Failed to load from CSV: {e}", flush=True)
            return self.store

    def load_from_ofac_sdn(self, filepath: str) -> PersonCanonicalStore:
        """
        Load person canonicals from OFAC SDN CSV format.

        OFAC SDN format (no headers):
        - Column 0: Entry ID (ent_num)
        - Column 1: Name (sdn_name)
        - Column 2: Type ("individual" or entity type)
        - Column 3: Program (e.g., SDGT, IRAN, etc.)
        - Column 4: Title
        - Columns 5-10: Various identifiers
        - Column 11: Remarks (contains DOB, nationality, etc.)

        Only loads records where type == "individual".
        """
        import hashlib

        try:
            print(f"[PERSON_CANONICALS] Loading from OFAC SDN: {filepath}", flush=True)

            persons = []
            individuals_found = 0
            entities_skipped = 0

            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                reader = csv.reader(f)

                for row in reader:
                    if len(row) < 3:
                        continue

                    ent_num = row[0].strip() if row[0] else ""
                    sdn_name = row[1].strip() if len(row) > 1 else ""
                    sdn_type = row[2].strip().lower() if len(row) > 2 else ""
                    program = row[3].strip() if len(row) > 3 else ""
                    remarks = row[11].strip() if len(row) > 11 else ""

                    # Only load individuals (skip entities/vessels/aircraft)
                    if sdn_type != "individual":
                        entities_skipped += 1
                        continue

                    individuals_found += 1

                    # Parse name (OFAC format: "LASTNAME, FIRSTNAME MIDDLENAME" or "LASTNAME, FIRSTNAME")
                    canonical_name = sdn_name
                    first_name = ""
                    last_name = ""
                    aliases = []

                    # Extract name parts
                    if "," in sdn_name:
                        parts = sdn_name.split(",", 1)
                        last_name = parts[0].strip()
                        first_name = parts[1].strip() if len(parts) > 1 else ""
                    else:
                        # No comma - treat as single name or last name
                        last_name = sdn_name

                    # Extract DOB and nationality from remarks
                    dob = ""
                    nationality = ""
                    if remarks and remarks != "-0-":
                        # DOB pattern: "DOB 10 Dec 1948" or "DOB 1938"
                        dob_match = re.search(r'DOB\s+(\d{1,2}\s+\w+\s+\d{4}|\d{4})', remarks)
                        if dob_match:
                            dob = dob_match.group(1)

                        # Nationality pattern: "nationality Egypt"
                        nat_match = re.search(r'nationality\s+(\w+)', remarks, re.I)
                        if nat_match:
                            nationality = nat_match.group(1)

                        # POB pattern: "POB Egypt" - use as nationality fallback
                        if not nationality:
                            pob_match = re.search(r'POB\s+([^;,]+)', remarks)
                            if pob_match:
                                nationality = pob_match.group(1).strip()

                        # Extract AKA aliases from remarks: "a.k.a. 'NAME'"
                        aka_matches = re.findall(r"a\.k\.a\.\s*'([^']+)'", remarks, re.I)
                        aliases.extend(aka_matches)

                    # Generate unique ID
                    person_id = f"SDN-{ent_num}"

                    person = {
                        "id": person_id,
                        "canonical_name": canonical_name,
                        "aliases": aliases,
                        "first_name": first_name,
                        "last_name": last_name,
                        "source": f"OFAC_SDN_{program}",
                        "metadata": {
                            "dob": dob,
                            "nationality": nationality,
                            "program": program,
                            "remarks": remarks[:500] if remarks and remarks != "-0-" else ""
                        }
                    }
                    persons.append(person)

            # Compute version hash
            version_hash = hashlib.md5(f"{len(persons)}_{filepath}".encode()).hexdigest()[:8]

            self.store.build_indexes(persons, f"ofac_sdn:{filepath}")
            print(f"[PERSON_CANONICALS] loaded={len(persons)} source=ofac_sdn version={version_hash}", flush=True)
            print(f"[PERSON_CANONICALS] OFAC stats: individuals={individuals_found}, entities_skipped={entities_skipped}", flush=True)

            return self.store

        except Exception as e:
            print(f"[PERSON_CANONICALS] Failed to load from OFAC SDN: {e}", flush=True)
            import traceback
            traceback.print_exc()
            return self.store

    def load_from_un_xml(self, filepath: str) -> List[Dict]:
        """
        Load person canonicals from UN Consolidated XML format.

        UN format:
        - Root: <CONSOLIDATED_LIST>
        - Individuals: <INDIVIDUALS><INDIVIDUAL>
        - Fields: <DATAID>, <FIRST_NAME>, <SECOND_NAME> (last name)
        - Aliases: <INDIVIDUAL_ALIAS><ALIAS_NAME>
        - DOB: <INDIVIDUAL_DATE_OF_BIRTH><YEAR>
        - Nationality: <NATIONALITY><VALUE>

        Returns list of person records (not stored yet - for multi-source merge).
        """
        persons = []

        try:
            print(f"[PERSON_CANONICALS] Loading from UN Consolidated: {filepath}", flush=True)

            tree = ET.parse(filepath)
            root = tree.getroot()

            # Find INDIVIDUALS section
            individuals = root.find("INDIVIDUALS")
            if individuals is None:
                print(f"[PERSON_CANONICALS] No INDIVIDUALS section in UN XML", flush=True)
                return persons

            for individual in individuals.findall("INDIVIDUAL"):
                data_id = individual.findtext("DATAID", "").strip()
                first_name = individual.findtext("FIRST_NAME", "").strip()
                second_name = individual.findtext("SECOND_NAME", "").strip()  # This is last name
                third_name = individual.findtext("THIRD_NAME", "").strip()
                un_list_type = individual.findtext("UN_LIST_TYPE", "").strip()
                comments = individual.findtext("COMMENTS1", "").strip()

                # Skip if no name
                if not first_name and not second_name:
                    continue

                # Build canonical name (UN format: FIRST LAST)
                name_parts = [p for p in [first_name, third_name, second_name] if p]
                canonical_name = " ".join(name_parts) if name_parts else ""

                # Extract aliases
                aliases = []
                for alias_elem in individual.findall("INDIVIDUAL_ALIAS"):
                    alias_name = alias_elem.findtext("ALIAS_NAME", "").strip()
                    if alias_name:
                        aliases.append(alias_name)

                # Extract DOB
                dob = ""
                dob_elem = individual.find("INDIVIDUAL_DATE_OF_BIRTH")
                if dob_elem is not None:
                    year = dob_elem.findtext("YEAR", "").strip()
                    if year:
                        dob = year

                # Extract nationality
                nationality = ""
                nat_elem = individual.find("NATIONALITY")
                if nat_elem is not None:
                    nationality = nat_elem.findtext("VALUE", "").strip()

                person = {
                    "id": f"UN-{data_id}",
                    "canonical_name": canonical_name,
                    "aliases": aliases,
                    "first_name": first_name,
                    "last_name": second_name,
                    "source": "UN",
                    "sources": [{"source": "UN", "source_id": f"UN-{data_id}"}],
                    "metadata": {
                        "dob": dob,
                        "nationality": nationality,
                        "program": un_list_type,
                        "remarks": comments[:500] if comments else ""
                    }
                }
                persons.append(person)

            print(f"[PERSON_CANONICALS] UN loaded={len(persons)} individuals", flush=True)

        except Exception as e:
            print(f"[PERSON_CANONICALS] Failed to load from UN XML: {e}", flush=True)
            import traceback
            traceback.print_exc()

        return persons

    def load_from_eu_xml(self, filepath: str) -> List[Dict]:
        """
        Load person canonicals from EU Consolidated XML format.

        EU format:
        - Root: <export xmlns="http://eu.europa.ec/fpi/fsd/export">
        - Entities: <sanctionEntity>
        - Filter: <subjectType code="person">
        - Names: <nameAlias firstName="" lastName="" wholeName="">
        - DOB: <birthdate year="">
        - Citizenship: <citizenship countryIso2Code="">

        Returns list of person records (not stored yet - for multi-source merge).
        """
        persons = []

        try:
            print(f"[PERSON_CANONICALS] Loading from EU Consolidated: {filepath}", flush=True)

            tree = ET.parse(filepath)
            root = tree.getroot()

            # Handle namespace
            ns = {"eu": "http://eu.europa.ec/fpi/fsd/export"}

            for entity in root.findall("eu:sanctionEntity", ns):
                logical_id = entity.get("logicalId", "")
                eu_ref = entity.get("euReferenceNumber", "")

                # Check if person
                subject_type = entity.find("eu:subjectType", ns)
                if subject_type is None or subject_type.get("code") != "person":
                    continue

                # Get primary name (first nameAlias with strong="true")
                primary_name = ""
                first_name = ""
                last_name = ""
                aliases = []

                for name_alias in entity.findall("eu:nameAlias", ns):
                    whole_name = name_alias.get("wholeName", "").strip()
                    fn = name_alias.get("firstName", "").strip()
                    ln = name_alias.get("lastName", "").strip()
                    is_strong = name_alias.get("strong", "false") == "true"

                    if not primary_name and whole_name and is_strong:
                        primary_name = whole_name
                        first_name = fn
                        last_name = ln
                    elif whole_name:
                        aliases.append(whole_name)

                if not primary_name:
                    continue

                # Extract DOB (first birthdate)
                dob = ""
                birthdate = entity.find("eu:birthdate", ns)
                if birthdate is not None:
                    year = birthdate.get("year", "")
                    if year:
                        dob = year

                # Extract nationality
                nationality = ""
                citizenship = entity.find("eu:citizenship", ns)
                if citizenship is not None:
                    nationality = citizenship.get("countryIso2Code", "")

                # Extract remarks
                remarks = ""
                remark_elem = entity.find("eu:remark", ns)
                if remark_elem is not None and remark_elem.text:
                    remarks = remark_elem.text.strip()

                person = {
                    "id": f"EU-{logical_id}",
                    "canonical_name": primary_name,
                    "aliases": aliases[:10],  # Limit aliases
                    "first_name": first_name,
                    "last_name": last_name,
                    "source": "EU",
                    "sources": [{"source": "EU", "source_id": f"EU-{logical_id}"}],
                    "metadata": {
                        "dob": dob,
                        "nationality": nationality,
                        "eu_reference": eu_ref,
                        "remarks": remarks[:500] if remarks else ""
                    }
                }
                persons.append(person)

            print(f"[PERSON_CANONICALS] EU loaded={len(persons)} individuals", flush=True)

        except Exception as e:
            print(f"[PERSON_CANONICALS] Failed to load from EU XML: {e}", flush=True)
            import traceback
            traceback.print_exc()

        return persons

    def load_multi_source(self, sources: List[str], data_dir: str) -> PersonCanonicalStore:
        """
        Load and merge multiple watchlist sources.

        Args:
            sources: List of source names (e.g., ["ofac", "un", "eu"])
            data_dir: Directory containing watchlist files

        Deduplication strategy:
        - Key = normalized primary name + DOB (if available)
        - If duplicate, merge sources list
        - Keep all aliases from all sources

        Returns store with merged, deduplicated records.
        """
        all_persons = []
        source_file_hashes = []
        source_counts = {}

        for source in sources:
            source_lower = source.lower()

            if source_lower == "ofac":
                filepath = os.path.join(data_dir, "ofac_sdn.csv")
                if os.path.exists(filepath):
                    # Get OFAC records
                    ofac_persons = self._load_ofac_raw(filepath)
                    all_persons.extend(ofac_persons)
                    source_counts["OFAC"] = len(ofac_persons)
                    source_file_hashes.append(self._file_hash(filepath))
                else:
                    print(f"[PERSON_CANONICALS] OFAC file not found: {filepath}", flush=True)

            elif source_lower == "un":
                filepath = os.path.join(data_dir, "un_consolidated.xml")
                if os.path.exists(filepath):
                    un_persons = self.load_from_un_xml(filepath)
                    all_persons.extend(un_persons)
                    source_counts["UN"] = len(un_persons)
                    source_file_hashes.append(self._file_hash(filepath))
                else:
                    print(f"[PERSON_CANONICALS] UN file not found: {filepath}", flush=True)

            elif source_lower == "eu":
                filepath = os.path.join(data_dir, "eu_consolidated.xml")
                if os.path.exists(filepath):
                    eu_persons = self.load_from_eu_xml(filepath)
                    all_persons.extend(eu_persons)
                    source_counts["EU"] = len(eu_persons)
                    source_file_hashes.append(self._file_hash(filepath))
                else:
                    print(f"[PERSON_CANONICALS] EU file not found: {filepath}", flush=True)

        # Deduplicate and merge
        merged = self._merge_persons(all_persons)

        # Compute version hash
        combined_hash = hashlib.sha256("".join(source_file_hashes).encode()).hexdigest()[:16]

        # Build store
        self.store.build_indexes(merged, f"multi:{','.join(sources)}")
        self.store.sources_loaded = sources
        self.store.source_counts = source_counts
        self.store.version_hash = combined_hash

        total_raw = sum(source_counts.values())
        print(f"[PERSON_CANONICALS] loaded_total={len(merged)} (raw={total_raw}) "
              f"sources={','.join(sources)} version={combined_hash}", flush=True)
        for src, count in source_counts.items():
            print(f"[PERSON_CANONICALS]   {src}: {count}", flush=True)

        return self.store

    def _load_ofac_raw(self, filepath: str) -> List[Dict]:
        """Load OFAC SDN and return raw person list (not stored)."""
        persons = []

        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                reader = csv.reader(f)

                for row in reader:
                    if len(row) < 3:
                        continue

                    ent_num = row[0].strip() if row[0] else ""
                    sdn_name = row[1].strip() if len(row) > 1 else ""
                    sdn_type = row[2].strip().lower() if len(row) > 2 else ""
                    program = row[3].strip() if len(row) > 3 else ""
                    remarks = row[11].strip() if len(row) > 11 else ""

                    if sdn_type != "individual":
                        continue

                    # Parse name
                    canonical_name = sdn_name
                    first_name = ""
                    last_name = ""
                    aliases = []

                    if "," in sdn_name:
                        parts = sdn_name.split(",", 1)
                        last_name = parts[0].strip()
                        first_name = parts[1].strip() if len(parts) > 1 else ""
                    else:
                        last_name = sdn_name

                    # Extract DOB and nationality
                    dob = ""
                    nationality = ""
                    if remarks and remarks != "-0-":
                        dob_match = re.search(r'DOB\s+(\d{1,2}\s+\w+\s+\d{4}|\d{4})', remarks)
                        if dob_match:
                            dob = dob_match.group(1)

                        nat_match = re.search(r'nationality\s+(\w+)', remarks, re.I)
                        if nat_match:
                            nationality = nat_match.group(1)

                        if not nationality:
                            pob_match = re.search(r'POB\s+([^;,]+)', remarks)
                            if pob_match:
                                nationality = pob_match.group(1).strip()

                        aka_matches = re.findall(r"a\.k\.a\.\s*'([^']+)'", remarks, re.I)
                        aliases.extend(aka_matches)

                    person = {
                        "id": f"SDN-{ent_num}",
                        "canonical_name": canonical_name,
                        "aliases": aliases,
                        "first_name": first_name,
                        "last_name": last_name,
                        "source": "OFAC",
                        "sources": [{"source": "OFAC", "source_id": f"SDN-{ent_num}"}],
                        "metadata": {
                            "dob": dob,
                            "nationality": nationality,
                            "program": program,
                            "remarks": remarks[:500] if remarks and remarks != "-0-" else ""
                        }
                    }
                    persons.append(person)

        except Exception as e:
            print(f"[PERSON_CANONICALS] Failed to load OFAC raw: {e}", flush=True)

        return persons

    def _merge_persons(self, persons: List[Dict]) -> List[Dict]:
        """
        Merge and deduplicate persons from multiple sources.

        Dedup key: normalized name + DOB year (if available)
        """
        merged = {}

        for person in persons:
            canonical = person.get("canonical_name", "")
            if not canonical:
                continue

            # Build dedup key
            normalized = PersonCanonicalStore.normalize_for_index(canonical)
            dob = person.get("metadata", {}).get("dob", "")
            # Extract year from DOB
            dob_year = ""
            if dob:
                year_match = re.search(r'\d{4}', str(dob))
                if year_match:
                    dob_year = year_match.group()

            dedup_key = f"{normalized}|{dob_year}"

            if dedup_key in merged:
                # Merge sources
                existing = merged[dedup_key]
                existing_sources = {s["source_id"] for s in existing.get("sources", [])}

                for src in person.get("sources", []):
                    if src["source_id"] not in existing_sources:
                        existing["sources"].append(src)

                # Merge aliases
                existing_aliases = set(existing.get("aliases", []))
                for alias in person.get("aliases", []):
                    if alias not in existing_aliases:
                        existing["aliases"].append(alias)
                        existing_aliases.add(alias)

                # Update source string
                source_names = sorted(set(s["source"] for s in existing["sources"]))
                existing["source"] = ",".join(source_names)

            else:
                merged[dedup_key] = person

        return list(merged.values())

    def _file_hash(self, filepath: str) -> str:
        """Compute SHA256 hash of a file."""
        sha256 = hashlib.sha256()
        try:
            with open(filepath, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    sha256.update(chunk)
            return sha256.hexdigest()[:16]
        except Exception:
            return "unknown"

    def load_empty(self) -> PersonCanonicalStore:
        """
        Return empty store (for when no watchlist is configured).
        """
        print(f"[PERSON_CANONICALS] No watchlist configured - person screening disabled", flush=True)
        self.store.build_indexes([], "none")
        return self.store


# Global store instance - loaded on first use
_person_store: Optional[PersonCanonicalStore] = None


def get_person_store() -> PersonCanonicalStore:
    """
    Get the global person canonical store, loading from configured source.

    Configuration via environment variables:
    - PERSON_WATCHLIST_SOURCES: Comma-separated list (e.g., "ofac,un,eu")
    - PERSON_CANONICALS_SOURCE: Legacy single-source config
    - PERSON_CANONICALS_COLLECTION: Firestore collection name (default: "person_canonicals")

    Multi-source (recommended):
        PERSON_WATCHLIST_SOURCES=ofac,un,eu

    Single-source (legacy):
        PERSON_CANONICALS_SOURCE=ofac_sdn
    """
    global _person_store

    if _person_store is not None:
        return _person_store

    loader = PersonCanonicalLoader()
    data_dir = os.path.join(os.path.dirname(__file__), "..", "data")

    # Check for multi-source config first
    multi_sources = os.getenv("PERSON_WATCHLIST_SOURCES", "")
    if multi_sources:
        sources = [s.strip() for s in multi_sources.split(",") if s.strip()]
        if sources:
            _person_store = loader.load_multi_source(sources, data_dir)
            return _person_store

    # Fall back to legacy single-source config
    source = os.getenv("PERSON_CANONICALS_SOURCE", "")

    if source == "firestore":
        collection = os.getenv("PERSON_CANONICALS_COLLECTION", "person_canonicals")
        _person_store = loader.load_from_firestore(collection)
    elif source.startswith("json:"):
        filepath = source[5:]
        _person_store = loader.load_from_json(filepath)
    elif source.startswith("csv:"):
        filepath = source[4:]
        _person_store = loader.load_from_csv(filepath)
    elif source.startswith("ofac:"):
        filepath = source[5:]
        _person_store = loader.load_from_ofac_sdn(filepath)
    elif source == "ofac_sdn":
        # Default OFAC path for TEST
        default_path = os.path.join(data_dir, "ofac_sdn.csv")
        if os.path.exists(default_path):
            _person_store = loader.load_from_ofac_sdn(default_path)
        else:
            print(f"[PERSON_CANONICALS] OFAC SDN file not found at {default_path}", flush=True)
            _person_store = loader.load_empty()
    elif source == "multi" or source == "all":
        # Load all available sources
        _person_store = loader.load_multi_source(["ofac", "un", "eu"], data_dir)
    else:
        # No source configured - return empty store
        _person_store = loader.load_empty()

    return _person_store


def get_watchlist_metadata() -> Dict:
    """
    Get metadata about loaded watchlists for audit/compliance.

    Returns:
        {
            "sources_loaded": ["OFAC", "UN", "EU"],
            "source_counts": {"OFAC": 7370, "UN": 800, "EU": 2500},
            "total_records": 10000,
            "version_hash": "abc123...",
            "deduplicated": True
        }
    """
    store = get_person_store()
    return {
        "sources_loaded": store.sources_loaded,
        "source_counts": store.source_counts,
        "total_records": store.record_count,
        "version_hash": store.version_hash,
        "deduplicated": len(store.sources_loaded) > 1
    }


def reload_person_store() -> PersonCanonicalStore:
    """Force reload of person canonicals from source."""
    global _person_store
    _person_store = None
    return get_person_store()
