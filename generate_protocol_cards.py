import re
import math
from collections import Counter

def get_words(text):
    return set(re.findall(r'\w+', text.lower()))

def jaccard_similarity(set1, set2):
    if not set1 or not set2:
        return 0
    intersection = len(set1.intersection(set2))
    union = len(set1.union(set2))
    return intersection / union

def main():
    # 1. Read existing cards
    existing_cards_text = []
    try:
        with open('anki_review_output/cards.txt', 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip().startswith('#') or not line.strip():
                    continue
                # strip out [tags]
                cleaned = re.sub(r'^(\[[^\]]+\]\s*)+', '', line.strip())
                existing_cards_text.append(cleaned)
    except FileNotFoundError:
        pass

    # 2. Parse comm_protocol_info.txt
    new_cards = []
    current_protocol = None

    with open('comm_protocol_info.txt', 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            
            # If no colon, it's a protocol header
            if ':' not in line:
                current_protocol = line.split('(')[0].strip()
                continue
            
            # It's a key-value pair
            if current_protocol:
                parts = line.split(':', 1)
                if len(parts) == 2:
                    category = parts[0].strip()
                    value = parts[1].strip()
                    
                    front = f"{current_protocol} {category}"
                    back = value
                    
                    card_text = f"{front} :: {back}"
                    
                    # Check for overlap
                    card_words = get_words(back)
                    is_overlap = False
                    
                    for existing in existing_cards_text:
                        existing_words = get_words(existing)
                        # if the value is mostly contained in an existing card, skip
                        # We use a simple containment/similarity metric
                        if len(card_words) > 0:
                            overlap_ratio = len(card_words.intersection(existing_words)) / len(card_words)
                            if overlap_ratio > 0.65:
                                is_overlap = True
                                break
                    
                    deck_name = f"Embedded::Hardware::Protocols::{current_protocol}"
                    formatted_card = f"[{deck_name}] {card_text}"
                    
                    if is_overlap:
                        new_cards.append(f"# OVERLAP: {formatted_card}")
                    else:
                        new_cards.append(formatted_card)

    with open('comm_protocol_cards.txt', 'w', encoding='utf-8') as f:
        for card in new_cards:
            f.write(card + '\n')
    
    print(f"Generated {len(new_cards)} cards. Output written to comm_protocol_cards.txt.")

if __name__ == '__main__':
    main()
