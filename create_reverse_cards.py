
import re

def get_context(signature):
    sig = signature.lower()
    if "sem_" in sig: return "semaphore"
    if "pthread_mutex" in sig: return "mutex"
    if "pthread_cond" in sig: return "condition variable"
    if "atomic_flag" in sig: return "atomic flag"
    if "atomic" in sig: return "atomic"
    if "pthread_spin" in sig: return "spinlock"
    return "api"

def main():
    with open("studying_dec16_anki.txt", "r") as f:
        lines = f.readlines()

    new_cards = []
    
    for line in lines:
        if line.startswith("API:"):
            parts = line.split(" :: ")
            if len(parts) != 2:
                continue
                
            # Part 0: "API: sem_wait(&sem) behavior"
            # Part 1: "Decrements count..."
            
            front_raw = parts[0].strip()
            description = parts[1].strip()
            
            # Extract clean signature from front_raw
            # Remove "API: " prefix
            signature = front_raw[5:].strip()
            
            # Remove optional trailing words like " behavior", " purpose", " signature" if mostly redundant?
            # Actually, keeping the full signature text as the "Back" of the reverse card is usually safest.
            # But the user might want just the function name if the front is descriptive enough.
            # Let's keep the user's request: "contextual heading like 'atomic: ' "
            
            context = get_context(signature)
            
            # Clean up description if needed (it's already the back of the original card)
            
            # Clean up signature for valid "Back" of reverse card. 
            # Original Front: "API: sem_wait(&sem) behavior" 
            # We probably want the Back of the reverse card to be just "sem_wait(&sem)" or the full original front text?
            # Let's use the full original front text minus "API: " to be precise.
            
            reverse_front = f"{context}: {description}"
            reverse_back = signature
            
            new_line = f"{reverse_front} :: {reverse_back}\n"
            new_cards.append(new_line)

    with open("reverse_cards.txt", "w") as f:
        f.write("\n# REVERSE API CARDS\n")
        f.writelines(new_cards)

if __name__ == "__main__":
    main()
