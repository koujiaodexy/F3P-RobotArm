"""Convert classifier scores into non-executable, reviewable suggestions only."""
import math

def decide(scores,catalog,gate):
    classes=catalog['classes']
    if len(scores)!=len(classes) or not scores or not all(math.isfinite(v) for v in scores):
        raise ValueError('Scores do not match the trained command catalog')
    order=sorted(range(len(scores)),key=scores.__getitem__,reverse=True)
    peak=scores[order[0]]
    values=[math.exp(v-peak) for v in scores];total=sum(values)
    softmax=[v/total for v in values]
    top,second=order[:2]
    report=dict(status='no_command',class_id=classes[top]['id'],class_index=top,
                softmax_score=softmax[top],top2_margin=softmax[top]-softmax[second],
                scores_are_calibrated_probabilities=False,executed=False,voice_authorizes_motion=False)
    if top<2: return report
    if softmax[top]<gate['min_softmax_score'] or report['top2_margin']<gate['min_top2_margin']:
        report['status']='uncertain';return report
    row=classes[top]
    report.update(status='proposal_only',text=row['name'],intent=row['id'],suggested_action=row['action'],
                  motion_confirmation_required=row['motion_confirmation_required'],
                  manual_confirmation_required=row['motion_confirmation_required'] or row['id']=='CONFIRM',
                  runtime_route_binding_required=row['id'].startswith('RUN_ROUTE_'))
    return report
