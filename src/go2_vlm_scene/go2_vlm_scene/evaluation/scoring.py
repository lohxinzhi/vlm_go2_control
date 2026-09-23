"""Conservative, explicit phrase scoring. No judge model or hidden room labels."""
import re


def words(text):
    return re.sub(r'[^a-z0-9 ]', ' ', text.lower().replace('-', ' '))


def phrase_pattern(phrase):
    return r'\b' + r'\s+'.join(re.escape(w) for w in words(phrase).split()) + r'\b'


def score_response(text, truth, aliases, success=True):
    expected = [(t['color'], t['shape']) for t in truth['expected_visible_targets']]
    score = {'target_score_status': 'scored', 'expected_target_count': len(expected),
        'predicted_targets': [], 'correct_target_detected': None, 'correct_colour': None,
        'correct_shape': None, 'missed_expected_target': None, 'hallucinated_coloured_target': None,
        'unsupported_scene_claim': None, 'exact_scene_success': None, 'manual_review_reasons': []}
    if not success:
        score['target_score_status'] = 'api_failed'
        return score
    normalized = words(text)
    candidates = {f'{color} {shape}': (color, canonical)
                  for color in aliases['colors'] for shape, canonical in aliases['shapes'].items()}
    reasons = score['manual_review_reasons']
    for phrase, target in aliases.get('aliases', {}).items():
        if target.get('approved') is True:
            candidates[phrase] = (target['color'], target['shape'])
        elif re.search(phrase_pattern(phrase), normalized):
            reasons.append('Unapproved alias: ' + phrase)
    if re.search(r'\b(no|not|without|maybe|might|possibly|perhaps|uncertain|cannot|can t|could|appears|seems)\b', normalized):
        reasons.append('Negation or uncertainty requires target review')
    if re.search(r'\b(two|three|four|five|six|seven|eight|nine|ten|several|multiple|[2-9][0-9]*)\b', normalized):
        reasons.append('Object counts require manual review')
    predicted, remainder = [], normalized
    for phrase in sorted(candidates, key=len, reverse=True):
        pattern = phrase_pattern(phrase)
        hits = list(re.finditer(pattern, remainder))
        if hits:
            predicted.extend([candidates[phrase]] * len(hits))
            remainder = re.sub(pattern, ' ', remainder)
    # Repeated references may be the same object; do not invent object counts.
    if len(predicted) != len(set(predicted)) or len(expected) != len(set(expected)):
        reasons.append('Repeated object labels require count/coreference review')
    target_remainder = remainder
    for phrase in truth.get('supported_scene_phrases', []):
        target_remainder = re.sub(phrase_pattern(phrase), ' ', target_remainder)
    target_words = list(aliases['colors']) + list(aliases['shapes']) + ['object', 'objects', 'block', 'box', 'tube']
    if not predicted or any(re.search(phrase_pattern(term) + r's?\b', target_remainder) for term in target_words):
        # A wall colour alone is not a target: conservative review, not hallucination.
        reasons.append('Unresolved colour/shape/object reference')
    score['predicted_targets'] = [{'color': c, 'shape': s} for c, s in predicted]
    if reasons:
        score['target_score_status'] = 'manual_review'
    else:
        predicted_set = set(predicted)
        expected_set = set(expected)
        true_positive = len(predicted_set & expected_set)
        remaining_predictions = list(predicted_set - expected_set)
        remaining_expected = list(expected_set - predicted_set)
        color_correct = shape_correct = true_positive
        # Exact matches first. Partial matches only when association is unambiguous.
        for color, shape in sorted(remaining_expected):
            same_color = [p for p in remaining_predictions if p[0] == color]
            same_shape = [p for p in remaining_predictions if p[1] == shape]
            options = same_color if same_color else same_shape
            if len(options) > 1:
                reasons.append('Ambiguous object association')
                score['target_score_status'] = 'manual_review'
                break
            if options:
                matched = options[0]
                associations = [e for e in remaining_expected if (e[0] == matched[0] if same_color else e[1] == matched[1])]
                if len(associations) > 1:
                    reasons.append('Ambiguous expected-object association')
                    score['target_score_status'] = 'manual_review'
                    break
                color_correct += matched[0] == color
                shape_correct += matched[1] == shape
                remaining_predictions.remove(matched)
        if score['target_score_status'] == 'scored':
            score.update(correct_target_detected=true_positive, correct_colour=color_correct,
                         correct_shape=shape_correct, missed_expected_target=len(expected_set)-true_positive,
                         hallucinated_coloured_target=len(predicted_set-expected_set))
    # Background assertions need separately human-confirmed visible evidence.
    unsupported = any(re.search(phrase_pattern(p), normalized)
                      for p in truth.get('unsupported_scene_phrases', []))
    for phrase in truth.get('supported_scene_phrases', []):
        remainder = re.sub(phrase_pattern(phrase), ' ', remainder)
    filler = set('a an the there is are one single sits sitting stands standing visible clearly seen '
                 'image shows show contains depicts scene view in on at of and with placed positioned '
                 'object it this that near beside next to appears be can see front centre center'.split())
    leftover = [w for w in remainder.split() if w not in filler]
    if unsupported:
        score['unsupported_scene_claim'] = True
    elif leftover:
        reasons.append('Unverified scene claim: ' + ' '.join(leftover))
    else:
        score['unsupported_scene_claim'] = False
    if score['target_score_status'] == 'scored' and score['unsupported_scene_claim'] is not None:
        score['exact_scene_success'] = (score['missed_expected_target'] == 0 and
            score['hallucinated_coloured_target'] == 0 and not score['unsupported_scene_claim'])
    return score
