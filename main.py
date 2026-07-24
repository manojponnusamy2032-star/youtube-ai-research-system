"""
main.py

Entry point for the YouTube AI Research System.
"""

from database.database_manager import create_tables

from utils.keyword_loader import load_keywords

from services import CollectorService


def main():

    print("=" * 60)
    print("YouTube AI Research Collector")
    print("=" * 60)

    create_tables()

    keywords = load_keywords()

    if not keywords:
        print("No keywords found.")
        return

    collector = CollectorService()

    total_found = 0
    total_saved = 0
    total_duplicates = 0

    for keyword in keywords:

        print("\n" + "=" * 60)
        print(f"Searching: {keyword}")
        print("=" * 60)

        found, saved, duplicates = collector.collect_keyword(keyword)

        total_found += found
        total_saved += saved
        total_duplicates += duplicates

        print(f"\nFinished '{keyword}'")
        print(f"New Videos : {saved}")
        print(f"Duplicates : {duplicates}")

    print("\n" + "=" * 60)
    print("FINAL REPORT")
    print("=" * 60)

    print(f"Keywords Processed : {len(keywords)}")
    print(f"Videos Found       : {total_found}")
    print(f"New Videos Saved   : {total_saved}")
    print(f"Duplicates Skipped : {total_duplicates}")

    print("=" * 60)


if __name__ == "__main__":
    main()