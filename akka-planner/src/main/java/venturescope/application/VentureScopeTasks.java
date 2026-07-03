package venturescope.application;

import akka.javasdk.agent.task.Task;

/**
 * Typed tasks for VentureScope.
 *
 * <p>Contrast with the LangGraph reconstruction: there is no graph, no state schema with
 * {@code iterations / decision_origin / recipes}, and no checkpoint plumbing. A task is a typed
 * unit of work; the runtime owns its lifecycle and persistence.
 */
public class VentureScopeTasks {

  /** The end result of a sizing engagement. */
  public record SomEstimate(String region, String currency, double som, String basis) {}

  /** A specialist sub-estimate (used by the delegation flexibility scenario). */
  public record SpecialistEstimate(String parameter, double value, String rationale) {}

  // prettier-ignore
  public static final Task<SomEstimate> SIZING = Task
    .define("Sizing")
    .description("Size a market opportunity (SOM) for a region, in the requested currency")
    .resultConformsTo(SomEstimate.class);

  // prettier-ignore
  public static final Task<SpecialistEstimate> SPECIALIST = Task
    .define("Specialist")
    .description("Produce a hard-to-source parameter estimate for a market")
    .resultConformsTo(SpecialistEstimate.class);
}
