package venturescope;

import static org.assertj.core.api.Assertions.assertThat;

import akka.javasdk.agent.task.TaskStatus;
import akka.javasdk.testkit.TestKit;
import akka.javasdk.testkit.TestKitSupport;
import akka.javasdk.testkit.TestModelProvider;
import java.util.concurrent.TimeUnit;
import org.awaitility.Awaitility;
import org.junit.jupiter.api.Test;
import venturescope.application.VentureScopePlanner;
import venturescope.application.VentureScopeTasks;

/**
 * Deterministic end-to-end run of the planner with a scripted model (no API key, no tokens).
 *
 * <p>The scripted model drives the exact acquisition sequence the LangGraph god node hard-codes as
 * routing: search population, ask the user for the target segment, search annual spend, calculate
 * SOM, then complete the task. Here that sequence is a model decision over tools, not graph edges.
 */
public class VentureScopePlannerTest extends TestKitSupport {

  private final TestModelProvider plannerModel = new TestModelProvider();

  @Override
  protected TestKit.Settings testKitSettings() {
    return TestKit.Settings.DEFAULT
      .withAdditionalConfig("akka.javasdk.agent.anthropic.api-key = n/a")
      .withModelProvider(VentureScopePlanner.class, plannerModel);
  }

  @Test
  public void sizesTheUsMarketEndToEnd() {
    // 1. Start -> look up population.
    plannerModel
      .whenMessage(msg -> msg.contains("US"))
      .reply(
        new TestModelProvider.ToolInvocationRequest(
          "VentureScopeTools_searchPopulation", "{\"region\":\"US\"}"));

    // 2. Population known -> ask user for the target segment fraction.
    plannerModel
      .whenToolResult(tr -> tr.name().equals("VentureScopeTools_searchPopulation"))
      .reply(
        new TestModelProvider.ToolInvocationRequest(
          "VentureScopeTools_askUser",
          "{\"question\":\"What fraction of the population is the target segment?\"}"));

    // 3. Segment known -> look up annual spend.
    plannerModel
      .whenToolResult(tr -> tr.name().equals("VentureScopeTools_askUser"))
      .reply(
        new TestModelProvider.ToolInvocationRequest(
          "VentureScopeTools_searchAnnualSpend", "{\"region\":\"US\"}"));

    // 4. All inputs -> calculate SOM.
    plannerModel
      .whenToolResult(tr -> tr.name().equals("VentureScopeTools_searchAnnualSpend"))
      .reply(
        new TestModelProvider.ToolInvocationRequest(
          "VentureScopeTools_calculateSom",
          "{\"population\":331000000,\"targetSegmentPct\":0.1,\"annualSpendPerUser\":240}"));

    // 5. Result in hand -> complete the task (currency stated -> guardrail passes).
    plannerModel
      .whenToolResult(tr -> tr.name().equals("VentureScopeTools_calculateSom"))
      .reply(
        new TestModelProvider.ToolInvocationRequest(
          "complete_task",
          "{\"region\":\"US\",\"currency\":\"USD\",\"som\":1191600000.0,"
            + "\"basis\":\"population * segment * adoption * annual spend\"}"));

    var taskId = componentClient
      .forAutonomousAgent(VentureScopePlanner.class, "test-1")
      .runSingleTask(VentureScopeTasks.SIZING.instructions("Size the US market opportunity."));

    Awaitility.await()
      .atMost(30, TimeUnit.SECONDS)
      .untilAsserted(() -> {
        var snapshot = componentClient.forTask(taskId).get(VentureScopeTasks.SIZING);
        assertThat(snapshot.status()).isEqualTo(TaskStatus.COMPLETED);
        assertThat(snapshot.result().currency()).isEqualTo("USD");
        assertThat(snapshot.result().som()).isEqualTo(1_191_600_000.0);
      });
  }
}
