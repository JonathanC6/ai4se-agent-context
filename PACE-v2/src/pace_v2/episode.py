"""两组共享动作协议、预算检查及工具；候选答案单独保留。"""
import json
from benchmarks.paper_pilot import FullHistory, question_prompt
from benchmarks.webwalkerqa import CHAT
from pace.context import BudgetExceeded, Builder
from pace.memory import Turn
from pace.policy import Settings
from pace.providers import ProviderError
from .actions import ACTION_PROMPT, RECOVERED, ActionInterface
from .context import EvidenceBuilder, PreparedMemory
from .evidence import Checklist


def solve(question,root,browser,api,counter,encoder,arm,checkpoint,budget=6000,max_steps=24,strategy=None):
    tools=browser.tools()
    system=ACTION_PROMPT+"\n"+"\n".join(f"{k} {v.description}" for k,v in tools.items())
    prompt=question_prompt(root,question)
    actor=ActionInterface(api,CHAT,counter,budget,80000,enforce_provider_budget=False,seed_query=question)
    book=None
    if arm in ("pace-v2","pace-v2-dag"):
        if (arm=="pace-v2-dag") != (strategy is not None):
            raise ValueError("DAG arm and strategy must agree")
        book=Checklist.plan(api,question)
        book.strategy=strategy
        system+=('\nUse the requested fact slots to guide searches. Bind dates, amounts, units, and years to '
                 'their subjects. Use glimpse {"ids":[1]} to recover compressed evidence. '
                 'After checking a draft, compose a fresh answer from supported facts. Avoid repeating failed routes.')
        memory=PreparedMemory(encoder)
        settings=Settings(20,budget=budget,pressure_mode="evidence-v2",compression_start_ratio=.9)
        if strategy:
            system+="\n"+strategy.instructions
        builder=EvidenceBuilder(system,prompt,memory,settings,counter,book,strategy)
    elif arm=="react":
        memory=FullHistory()
        builder=Builder(system,prompt,memory,Settings(20,budget=budget,recent=max_steps+1,glimpse_limit=0),
                        counter,trace_window=True)
    else:
        raise ValueError("unknown arm")
    result=dict(status="running",answer=None,steps=[],drafts=[],history=[],actor_episode_id=actor.episode_id)
    reviews=0
    allowed=set(tools) | {"finish"}
    if book:
        allowed.add("glimpse")

    def save():
        if book:
            result["checklist"]=book.state()
            result["events"]=book.events
        checkpoint(result)

    save()
    for step in range(1,max_steps+1):
        try:
            ctx=builder.build()
            reply=actor.decide(ctx.messages,result["drafts"],allowed)
        except BudgetExceeded as exc:
            result.update(status="budget_exceeded",error=str(exc),budget_stop_window=builder.last_window)
            break
        if reply is None:
            result.update(status="no_valid_answer",error="No usable action or direct answer",stop_step=step)
            break
        actual=api.last_input_tokens.get("actor")
        trace=ctx.trace()
        sent=counter.messages(actor.last_messages)
        trace.update(action=reply,input_tokens_actual=actual,input_tokens_estimate=sent,
                     input_count_error=sent-actual if type(actual) is int and actual>0 else None)
        result["steps"].append(trace)
        name,args=reply["tool"],reply["args"]
        review=None
        if name=="finish" and isinstance(args.get("answer"),str) and args["answer"].strip():
            draft=args["answer"].strip()
            if reply.get("origin") in RECOVERED:
                result.update(status="finished",answer=draft,submission_state=reply["origin"])
                break
            result["drafts"].append(dict(step=step,answer=draft))
            save()
            if book and step<max_steps and reviews<2:
                review=book.review(api,draft,ctx,browser.evidence)
            if review is None:
                reason=("actor_finish" if not book else "last_step" if step==max_steps else
                        "review_limit" if reviews>=2 else "no_further_review")
                result.update(status="finished",answer=draft,submission_state=reason)
                break
            reviews+=1
            name,args=review["tool"],review["args"]
            trace["review"]=review
        restored=[]
        try:
            if name=="glimpse" and book:
                obs=memory.glimpse(args.get("ids"),3)
                restored=args["ids"]
            elif name in tools:
                obs=tools[name].call(args)
            else:
                raise ValueError("choose an enabled tool and valid arguments")
        except ProviderError as exc:
            obs=f"Tool error: {exc}"
            trace["tool_error"]=obs
            if result["drafts"]:
                result.update(status="finished",answer=result["drafts"][-1]["answer"],
                              submission_state="saved_draft_after_tool_error")
                break
        except (ValueError,KeyError,TypeError) as exc:
            obs=f"Tool error: {exc}"
        action=json.dumps(dict(tool=name,args=args),ensure_ascii=False,sort_keys=True)
        turn=Turn(str(reply.get("note",""))[:220] if not review else review["goal"],action,obs,name)
        added=[]
        if book:
            fact_count=len(book.facts)
            summary,added=book.digest(api,name,obs,step,browser.evidence,restored)
            chunk=memory.store(turn,summary)
            if strategy:
                visible={r.chunk.id for r in ctx.selections}
                trace["metadata"]=strategy.record(chunk.id,{} if review else reply,visible,obs.startswith("Tool error:"))
        else:
            memory.append(turn)
        result["history"].append(dict(id=step,kind=name,action=action,observation=obs))
        if book:
            result["history"][-1]["summaries"]={"detailed":summary.detailed,"brief":summary.brief}
            trace["new_bound_slots"]=added
        if review:
            trace["recovery"]={"tool_ok":not obs.startswith("Tool error:"),"slot":review["slot"],
                               "new_bound_evidence":review["slot"] in added,
                               "finding":book.check_recovery(api,review,book.facts[fact_count:])}
        save()
    if result["status"]=="running":
        result["status"]="step_limit"
    save()
    return result
