package venturescope.application;

import akka.javasdk.agent.autonomous.AgentDefinition;
import akka.javasdk.agent.autonomous.AutonomousAgent;
import akka.javasdk.agent.autonomous.capability.Delegation;
import akka.javasdk.agent.autonomous.capability.TaskAcceptance;
import akka.javasdk.annotations.Component;

/**
 * VentureScope planner as a single AutonomousAgent.
 *
 * <p>This entire class is the counterpart to the LangGraph god node PLUS its 8-node graph PLUS its
 * hand-rolled iteration/checkpoint/event plumbing. There is no {@code plan_node}, no
 * {@code StateGraph}, no conditional edges, no {@code max_iters} bookkeeping, and no serialization
 * schema. The durable model-driven loop, progress persistence, iteration caps, and the audit event
 * stream are all provided by the runtime.
 *
 * <ul>
 *   <li>{@code goal} — replaces the intent buried across the god node's branches.
 *   <li>{@code tools} — search / ask_user / calculate become plain callable methods.
 *   <li>{@code responseGuardrails} — governance policy as an isolated, traced unit.
 *   <li>{@code TaskAcceptance.maxIterationsPerTask} — the iteration cap, declared not coded.
 *   <li>{@code Delegation} — hand a hard parameter to a specialist; a one-line capability.
 * </ul>
 */
@Component(id = "venturescope-planner")
public class VentureScopePlanner extends AutonomousAgent {

  @Override
  public AgentDefinition definition() {
    return define()
      .goal(
        """
        Size the market opportunity (SOM) for the requested region. Collect the \
        population, target-segment fraction, and average annual spend per user — \
        obtaining each from web search or from the user as appropriate — then \
        compute the SOM and report it in the requested currency, explaining the \
        basis. Ask the user for the region and currency first if they are not given. \
        """
      )
      .tools(new VentureScopeTools())
      .responseGuardrails(CurrencyPolicyGuard.class)
      .capability(
        TaskAcceptance.of(VentureScopeTasks.SIZING).maxIterationsPerTask(8)
      )
      .capability(Delegation.to(MarketSpecialist.class));
  }
}
