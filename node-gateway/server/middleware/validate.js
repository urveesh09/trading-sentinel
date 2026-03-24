const { ValidationError } = require('../utils/errors');

/**
 * Validates req.body, req.query, or req.params against a Zod schema.
 * @param {import('zod').ZodSchema} schema
 * @param {'body' | 'query' | 'params'} property
 */
const validate = (schema, property = 'body') => {
  return (req, res, next) => {
    try {
      // Parse throws if invalid, stripping unknown keys if schema is configured to do so
      const validData = schema.parse(req[property]);
      
      // Reassign the validated (and potentially coerced/transformed) data back to the request
      req[property] = validData;
      next();
    } catch (error) {
      // Map Zod errors to a single readable string for the client
      const errorMsg = error.errors?.map(e => `${e.path.join('.')}: ${e.message}`).join(', ') || 'Invalid payload';
      
      // Pass the domain-specific ValidationError to the global error handler
      next(new ValidationError(`Validation failed: ${errorMsg}`));
    }
  };
};

module.exports = { validate };
