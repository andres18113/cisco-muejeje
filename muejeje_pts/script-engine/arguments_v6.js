/*
 * Muejeje runtime — an operation's own arguments.
 *
 * `validation_v6.js` decides whether a caller's string is a V6 envelope at all
 * and bounds what that envelope may carry. This file decides whether the
 * arguments inside it are the ones a *particular* operation admits, against the
 * rules that operation declares for itself.
 *
 * Two responsibilities, two files, and the split is the line budget doing what
 * it is for (MJ-018, MJ-020): an envelope rule holds for every request, while
 * an argument rule belongs to one operation and grows with the whitelist.
 *
 * It knows no more about operations than `validation_v6.js` does: the rules
 * arrive as data from the dispatcher, and nothing here reads the whitelist
 * (MJ-019). Refusals here are `INVALID_ARGS`; the envelope's own refusals stay
 * `INVALID_REQUEST`, because a bound on the envelope and a rule of an
 * operation are different contracts (MJ-022, MJ-029).
 */

/* Arguments are whitelisted per operation, by name, and each admitted name
 * carries the rule its value must satisfy. An operation that takes none
 * declares an empty rule set and accepts an empty object and nothing else.
 *
 * A rule may also say the argument is required. An operation asks for that
 * only when no default could be honest — where every value in the space is a
 * different question, and choosing one would answer a question the caller did
 * not ask. A missing required argument is `INVALID_ARGS`, which is what "a
 * whitelisted operation given arguments it does not support" already means; it
 * is not a reading, because nothing was read (MJ-022, MJ-029). */
function muejejeV6ArgsError(args, rules) {
    var supplied = muejejeV6OwnKeys(args);
    for (var i = 0; i < supplied.length; i++) {
        var name = supplied[i];
        if (!Object.prototype.hasOwnProperty.call(rules, name)) {
            return "args carries a field this operation does not support";
        }
        var reason = muejejeV6ArgValueError(args[name], rules[name]);
        if (reason !== null) {
            return reason;
        }
    }
    return muejejeV6MissingArgError(args, rules);
}

function muejejeV6MissingArgError(args, rules) {
    var declared = muejejeV6OwnKeys(rules);
    for (var i = 0; i < declared.length; i++) {
        if (
            rules[declared[i]].required === true
            && !Object.prototype.hasOwnProperty.call(args, declared[i])
        ) {
            return "args omits a field this operation requires";
        }
    }
    return null;
}

/* One rule kind so far. An unrecognised kind refuses the argument rather than
 * admitting it: a rule the kernel cannot read bounds nothing. */
function muejejeV6ArgValueError(value, rule) {
    if (rule.kind === "integer") {
        if (typeof value !== "number" || value % 1 !== 0) {
            return "an argument of this operation must be a whole number";
        }
        if (value < rule.min || value > rule.max) {
            return "an argument of this operation is outside its bounds";
        }
        return null;
    }
    return "this operation declares no readable rule for that argument";
}
