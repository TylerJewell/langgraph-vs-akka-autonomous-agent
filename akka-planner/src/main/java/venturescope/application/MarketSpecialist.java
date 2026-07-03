package venturescope.application;

import akka.javasdk.agent.autonomous.AgentDefinition;
import akka.javasdk.agent.autonomous.AutonomousAgent;
import akka.javasdk.agent.autonomous.capability.TaskAcceptance;
import akka.javasdk.annotations.Component;

/**
 * A specialist the planner can delegate a hard-to-source parameter to.
 *
 * <p>This is the "flexibility" scenario: adding a specialist is a new agent plus one
 * {@code Delegation.to(...)} line on the planner — no graph surgery. In LangGraph the same change
 * means new nodes, new edges, new routing, and new checkpoint boundaries.
 */
@Component(
  id = "market-specialist",
  description = "Estimates hard-to-source market parameters (e.g. niche adoption rates)"
)
public class MarketSpecialist extends AutonomousAgent {

  @Override
  public AgentDefinition definition() {
    return define()
      .goal(
        """
        Produce a defensible estimate for the requested hard-to-source market \
        parameter, stating the reasoning and any assumptions. \
        """
      )
      .capability(TaskAcceptance.of(VentureScopeTasks.SPECIALIST).maxIterationsPerTask(4));
  }
}
