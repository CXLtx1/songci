import subprocess
import sys

SCRIPTS = {
    "1": ("generator", "generate/generator.py"),
    "2": ("extract_imagery", "generate/extract_imagery.py"),
    "3": ("pytorch-analysis", "analyze/pytorch-analysis.py"),
    "4": ("pytorch-analysis-2", "analyze/pytorch-analysis-2.py"),
    "5": ("pytorch-analysis-real", "analyze/pytorch-analysis-real.py"),
    "6": ("pytorch-human-analysis", "analyze/pytorch-human-analysis.py"),
    "7": ("pytorch-real-identical", "analyze/pytorch-real-identical.py"),
    "8": ("pytorch-every_sentence", "analyze/pytorch-every_sentence.py"),
    "9": ("ai-net", "analyze/ai-net.py"),
    "10": ("ai-net-2", "analyze/ai-net-2.py"),
    "11": ("analyze-1", "analyze/analyze-1.py"),
    "12": ("engine-test", "scripts/engine-test.py"),
    "13": ("pytorch-analysis-3", "analyze/pytorch-analysis-3.py"),
    "14": ("pytorch-analysis-4", "analyze/pytorch-analysis-4.py"),
    "15": ("neo-analysis", "analyze/neo-analysis.py"),
    "16": ("neo-real-analysis", "analyze/neo-real-analysis.py")
}

def main():
    print("=" * 50)
    print("SongCi Project Launcher")
    print("=" * 50)
    print("\nAvailable scripts:\n")
    for key, (name, _) in SCRIPTS.items():
        print(f"  {key}. {name}")
    print("\n  0. Exit")
    print()
    
    choice = input("Select script to run: ").strip()
    
    if choice == "0":
        print("Exiting...")
        return
    
    if choice not in SCRIPTS:
        print(f"Invalid choice: {choice}")
        return
    
    name, script_path = SCRIPTS[choice]
    print(f"\nRunning {name}...\n")
    print("-" * 50)
    
    subprocess.run([sys.executable, script_path])

if __name__ == "__main__":
    main()
