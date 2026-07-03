package venturescope.application;

import akka.javasdk.agent.GuardrailContext;
import akka.javasdk.agent.TextGuardrail;

/**
 * Governance-as-code: every planner result must state the currency it is expressed in.
 *
 * <p>This is the governance contrast with the LangGraph god node, where such a policy would be
 * one more branch smeared into {@code plan_node}. Here it is an isolated, named, testable unit
 * that the runtime evaluates, logs, meters, and traces on every model response — enforcement
 * lives in the runtime, not in agent code.
 */
public class CurrencyPolicyGuard implements TextGuardrail {

  private static final String[] KNOWN = {"USD", "EUR", "GBP", "JPY", "SGD"};

  public CurrencyPolicyGuard(GuardrailContext context) {
    // context.config() available for externalised policy config; not needed here.
  }

  @Override
  public Result evaluate(String text) {
    String upper = text.toUpperCase();
    for (String code : KNOWN) {
      if (upper.contains(code)) return Result.OK;
    }
    // A monetary figure with no currency is a compliance violation for financial outputs.
    if (text.matches(".*\\d.*")) {
      return new Result(false, "Monetary output must state an explicit currency (e.g. USD).");
    }
    return Result.OK;
  }
}
