from collector.database import create_tables, insert_video
from collector.youtube import search_videos


def main():

    print("=" * 50)
    print("YouTube Research Collector")
    print("=" * 50)

    create_tables()

    keyword = input("\nEnter search keyword: ")

    print(f"\nSearching YouTube for '{keyword}'...\n")

    videos = search_videos(keyword, max_results=10)

    print(f"Found {len(videos)} videos\n")

    saved = 0

    for video in videos:
        insert_video(video)
        saved += 1

        print(f"Saved: {video['title']}")

    print("\n" + "=" * 50)
    print(f"Finished! Saved {saved} videos.")
    print("=" * 50)


if __name__ == "__main__":
    main()