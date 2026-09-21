/**
 * Textes de la page de remerciement. Une seule implementation, utilisee par le
 * formulaire public et par l'apercu du tunnel.
 */
const NAME_KEYS = ["name", "prenom", "first_name", "fullname", "full_name"];

export function firstNameFrom(answers: Record<string, unknown>): string {
  const key = NAME_KEYS.find(candidate => typeof answers[candidate] === "string" && String(answers[candidate]).trim());
  if (!key) return "";
  return String(answers[key]).trim().split(/\s+/)[0];
}

/** Remplace {prenom} par le prenom, ou retire proprement le gabarit et sa ponctuation. */
export function thankYouTitle(title: string | undefined, answers: Record<string, unknown> = {}): string {
  const template = title || "Merci !";
  const firstName = firstNameFrom(answers);
  if (firstName) return template.replace(/\{prenom\}/g, firstName);
  // Sans prenom : on retire le gabarit en gardant la typographie francaise
  // (espace avant ! et ?, pas avant . et ,).
  return template.replace(/\s*\{prenom\}\s*/g, " ").replace(/\s+([.,])/g, "$1").replace(/\s{2,}/g, " ").trim();
}
