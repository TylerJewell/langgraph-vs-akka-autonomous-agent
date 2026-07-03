package venturescope.api;

import akka.javasdk.annotations.Acl;
import akka.javasdk.annotations.http.Get;
import akka.javasdk.annotations.http.HttpEndpoint;
import akka.javasdk.annotations.http.Post;
import akka.javasdk.client.ComponentClient;
import akka.stream.Materializer;
import java.util.UUID;
import venturescope.application.VentureScopePlanner;
import venturescope.application.VentureScopeTasks;

/**
 * HTTP surface for the planner.
 *
 * <p>Governance highlight: {@code create} subscribes to the runtime's notification stream BEFORE
 * starting the task, so every iteration, token count, task transition, and struggle signal is
 * captured as a first-class audit event — with zero instrumentation in the agent. Contrast the
 * LangGraph reconstruction, which hand-appends to {@code state["events"]} in every node.
 */
@Acl(allow = @Acl.Matcher(principal = Acl.Principal.INTERNET))
@HttpEndpoint("/sizing")
public class VentureScopeEndpoint {

  public record SizingRequest(String brief) {}

  public record SizingResponse(String id) {}

  public record SizingStatus(String status, VentureScopeTasks.SomEstimate result) {}

  private final ComponentClient componentClient;
  private final Materializer materializer;

  public VentureScopeEndpoint(ComponentClient componentClient, Materializer materializer) {
    this.componentClient = componentClient;
    this.materializer = materializer;
  }

  @Post
  public SizingResponse create(SizingRequest request) {
    var instanceId = UUID.randomUUID().toString();

    // Free audit trail: subscribe before triggering to catch early events.
    componentClient
      .forAutonomousAgent(VentureScopePlanner.class, instanceId)
      .notificationStream()
      .runForeach(n -> System.out.println("[audit] " + n), materializer);

    var taskId = componentClient
      .forAutonomousAgent(VentureScopePlanner.class, instanceId)
      .runSingleTask(VentureScopeTasks.SIZING.instructions(request.brief()));

    return new SizingResponse(taskId);
  }

  @Get("/{taskId}")
  public SizingStatus get(String taskId) {
    var snapshot = componentClient.forTask(taskId).get(VentureScopeTasks.SIZING);
    return new SizingStatus(snapshot.status().name(), snapshot.result());
  }
}
