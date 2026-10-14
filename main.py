"""Start the game: python main.py   (sound check: python main.py --audio-test)"""
import sys

if __name__ == "__main__":
    if "--audio-test" in sys.argv[1:]:
        from game.audio import audio_test
        sys.exit(audio_test())
    from game.app import run
    run()
