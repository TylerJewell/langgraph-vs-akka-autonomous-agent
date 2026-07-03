package venturescope.application;

import akka.javasdk.annotations.FunctionTool;

/**
 * The planner's tools. Each corresponds to one node in the LangGraph god graph
 * (search / ask_user / calculate) — but here they are just methods the model may
 * call. There is no routing logic, no edges, and no "which node next" decision to
 * encode: the runtime's model-driven loop selects the next tool.
 *
 * <p>ask_user note: Akka's first-class durable human-input gate ("External input
 * capability") is on the roadmap, not yet shipped. Until then, human answers are
 * modelled as a tool that reads from an answer source. Here it returns canned
 * answers so the demo runs offline; in production this would read a KeyValueEntity
 * that an HTTP endpoint writes the user's reply into.
 */
public class VentureScopeTools {

  @FunctionTool(description = "Look up the population of a region via web search.")
  public double searchPopulation(String region) {
    return switch (region.toUpperCase()) {
      case "US", "USA", "UNITED STATES" -> 331_000_000d;
      case "EU" -> 448_000_000d;
      case "SEA" -> 680_000_000d;
      default -> 100_000_000d;
    };
  }

  @FunctionTool(description = "Look up the average annual spend per user for a region via web search.")
  public double searchAnnualSpend(String region) {
    return switch (region.toUpperCase()) {
      case "US", "USA", "UNITED STATES" -> 240d;
      case "EU" -> 200d;
      default -> 120d;
    };
  }

  @FunctionTool(
    description = "Ask the user a question and return their answer. Use for parameters that cannot be found via search."
  )
  public String askUser(String question) {
    // Roadmap: replace with the durable External-input capability. Canned for the demo.
    String q = question.toLowerCase();
    if (q.contains("segment")) return "0.1";
    if (q.contains("currency")) return "USD";
    if (q.contains("region")) return "US";
    return "unknown";
  }

  @FunctionTool(
    description = "Compute the Serviceable Obtainable Market (SOM) from the collected parameters."
  )
  public double calculateSom(double population, double targetSegmentPct, double annualSpendPerUser) {
    double adoptionRate = Math.min(0.9, targetSegmentPct * 1.5);
    return population * targetSegmentPct * adoptionRate * annualSpendPerUser;
  }
}
